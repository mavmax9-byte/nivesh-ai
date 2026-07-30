"""News & Sentiment Analyst.

Implements `BaseAgent` (agents/base.py), following the exact same shape as
`TechnicalAnalystAgent` (see that module's docstring for the `run()`
flow this mirrors) -- only the evidence types, query, prompt, and output
schema differ.
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError

from nivesh.ai_agents.agents.base import AgentContext, AgentFinding, BaseAgent
from nivesh.ai_agents.agents.news_sentiment.prompts import (
    NEWS_SENTIMENT_ANALYST_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_user_prompt,
)
from nivesh.ai_agents.agents.news_sentiment.queries import (
    NEWS_SENTIMENT_ANALYSIS_QUERY,
    RELEVANT_EVIDENCE_TYPES,
)
from nivesh.ai_agents.agents.news_sentiment.schemas import (
    LLMNewsSentimentOutput,
    NewsSentimentAnalysisResult,
)
from nivesh.ai_agents.agents.news_sentiment.validation import (
    EVIDENCE_CONFIDENCE_FLOOR,
    compute_evidence_confidence,
)
from nivesh.ai_agents.guardrails import (
    check_no_investment_advice,
    compute_confidence_score,
    drop_unsupported_assessments,
    resolve_citation_refs,
)
from nivesh.ai_agents.providers.base import LLMProvider
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.retrieval_engine.normalization import EvidenceItem
from nivesh.retrieval_engine.service import RetrievalEngineService

logger = logging.getLogger(__name__)

AGENT_CODE = "news_sentiment_analyst"

EVIDENCE_LIMIT = 30


class NewsSentimentAnalystAgent(BaseAgent):
    agent_code = AGENT_CODE

    def __init__(
        self,
        retrieval_service: RetrievalEngineService,
        llm_provider: LLMProvider,
        company_repository: CompanyRepository,
        shared_evidence: list[EvidenceItem] | None = None,
    ) -> None:
        self._retrieval = retrieval_service
        self._llm = llm_provider
        self._companies = company_repository
        self._shared_evidence = shared_evidence

    async def run(self, context: AgentContext) -> AgentFinding:
        company = await self._companies.get_by_id(uuid.UUID(context.company_id))
        if company is None:
            raise NotFoundError(f"No company found with id '{context.company_id}'")
        symbol = company.symbol

        if self._shared_evidence is None:
            package = await self._retrieval.build_context_package(
                symbol, NEWS_SENTIMENT_ANALYSIS_QUERY, limit=EVIDENCE_LIMIT
            )
            pool = list(package.evidence)
        else:
            pool = self._shared_evidence
        evidence = [item for item in pool if item.source_type in RELEVANT_EVIDENCE_TYPES]

        evidence_confidence = compute_evidence_confidence(evidence)
        if evidence_confidence <= EVIDENCE_CONFIDENCE_FLOOR:
            logger.info(
                "news_sentiment_analysis_insufficient_evidence",
                extra={"symbol": symbol, "evidence_count": len(evidence)},
            )
            result = self._insufficient_evidence_result(symbol, evidence_confidence)
        else:
            result = await self._analyze(symbol, evidence, evidence_confidence)

        return AgentFinding(
            agent_code=AGENT_CODE,
            summary=result.summary,
            confidence_score=result.confidence_score,
            evidence_ids=[str(citation.source_id) for citation in result.citations],
            detail=result.model_dump(mode="json"),
        )

    # -- internals -----------------------------------------------------

    async def _analyze(
        self, symbol: str, evidence: list[EvidenceItem], evidence_confidence: float
    ) -> NewsSentimentAnalysisResult:
        user_prompt = build_user_prompt(symbol, NEWS_SENTIMENT_ANALYSIS_QUERY, evidence)
        completion = await self._llm.complete(
            NEWS_SENTIMENT_ANALYST_SYSTEM_PROMPT,
            user_prompt,
            LLMNewsSentimentOutput.model_json_schema(),
        )

        try:
            llm_output = LLMNewsSentimentOutput.model_validate(completion.parsed_json)
        except ValidationError as exc:
            raise LLMResponseParsingError(
                f"LLM response did not match the expected schema: {exc}"
            ) from exc

        findings, dropped_findings = drop_unsupported_assessments(
            llm_output.findings, len(evidence)
        )

        check_no_investment_advice(
            llm_output.summary,
            llm_output.sentiment_assessment,
            *(assessment.observation for assessment in findings),
        )

        citations = resolve_citation_refs(findings, evidence)
        confidence_score = compute_confidence_score(evidence_confidence, llm_output.llm_confidence)

        caveats: list[str] = []
        if dropped_findings:
            caveats.append(
                f"{dropped_findings} claim(s) were removed for citing evidence outside the "
                f"provided reference list."
            )

        return NewsSentimentAnalysisResult(
            company_symbol=symbol,
            summary=llm_output.summary,
            findings=findings,
            sentiment_assessment=llm_output.sentiment_assessment,
            evidence_sufficiency=llm_output.evidence_sufficiency,
            confidence_score=confidence_score,
            citations=citations,
            caveats=caveats,
            prompt_version=PROMPT_VERSION,
            model_used=completion.model,
            generated_at=datetime.now(UTC),
        )

    def _insufficient_evidence_result(
        self, symbol: str, evidence_confidence: float
    ) -> NewsSentimentAnalysisResult:
        return NewsSentimentAnalysisResult(
            company_symbol=symbol,
            summary=(
                "Insufficient evidence is available to produce a news sentiment analysis for "
                "this company."
            ),
            findings=[],
            sentiment_assessment="No news or research summary evidence was found, so sentiment "
            "cannot be assessed.",
            evidence_sufficiency="insufficient",
            confidence_score=evidence_confidence,
            citations=[],
            caveats=[
                "No news article or research summary evidence was found for this company. Run "
                "a news sync before requesting news sentiment analysis."
            ],
            prompt_version=PROMPT_VERSION,
            model_used="none",
            generated_at=datetime.now(UTC),
        )

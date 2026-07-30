"""Fundamental Analyst -- the first concrete specialist agent.

Implements `BaseAgent` (agents/base.py). Analyzes a company's financial
fundamentals (financial statements, corporate filings, filing-derived
document sections, research-dossier summaries, company profile) using
only evidence `retrieval_engine` already ranked and deduplicated -- this
agent adds zero retrieval logic of its own (see queries.py and
FUNDAMENTAL_ANALYST_DESIGN.md §2/§3). It never recommends a trade, a
price target, or personalized investment advice -- see validation.py's
`check_no_investment_advice`, a deterministic guardrail that does not
rely on the model "remembering" the system prompt's instruction.

Confidence is never purely LLM-self-reported (see validation.py's
`compute_evidence_confidence`/`compute_confidence_score`) -- a
deterministic, pre-LLM evidence-coverage signal always caps what the
model's own self-reported confidence can raise the final score to. When
that signal is at its floor (no financial_statement evidence at all),
the LLM is never called at all -- an explicit "insufficient evidence"
finding is returned instead of guessing (§8/§9).

A failed or unparseable LLM call is never silently swallowed into a
placeholder finding -- unlike retrieval_engine's semantic leg (which
degrades gracefully because "fewer evidence items" is still an honest
result), a "finding" produced without the LLM actually reasoning would be
fabricated output, which ai_agents' own docstring (orchestrator.py) already
rules out. LLMProviderError/LLMResponseParsingError simply propagate to
the Celery task layer, which retries like any other failure (see
ingestion/tasks.py).
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError

from nivesh.ai_agents.agents.base import AgentContext, AgentFinding, BaseAgent
from nivesh.ai_agents.agents.fundamental.prompts import (
    FUNDAMENTAL_ANALYST_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_user_prompt,
)
from nivesh.ai_agents.agents.fundamental.queries import (
    FUNDAMENTAL_ANALYSIS_QUERY,
    RELEVANT_EVIDENCE_TYPES,
)
from nivesh.ai_agents.agents.fundamental.schemas import (
    FundamentalAnalysisResult,
    LLMFundamentalOutput,
)
from nivesh.ai_agents.agents.fundamental.validation import (
    EVIDENCE_CONFIDENCE_FLOOR,
    check_no_investment_advice,
    compute_confidence_score,
    compute_evidence_confidence,
    drop_unsupported_assessments,
    resolve_citation_refs,
)
from nivesh.ai_agents.providers.base import LLMProvider
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.retrieval_engine.models import EVIDENCE_SOURCE_FINANCIAL_STATEMENT
from nivesh.retrieval_engine.normalization import EvidenceItem
from nivesh.retrieval_engine.service import RetrievalEngineService

logger = logging.getLogger(__name__)

AGENT_CODE = "fundamental_analyst"

# Larger than retrieval_engine's own DEFAULT_LIMIT=20, since fundamentals
# analysis wants several financial statement periods and filings in view
# at once, and the client-side RELEVANT_EVIDENCE_TYPES filter drops a
# nontrivial fraction of whatever comes back (technical indicators,
# news). A starting guess, not empirically tuned -- see design doc §3.
EVIDENCE_LIMIT = 30


class FundamentalAnalystAgent(BaseAgent):
    agent_code = AGENT_CODE

    def __init__(
        self,
        retrieval_service: RetrievalEngineService,
        llm_provider: LLMProvider,
        company_repository: CompanyRepository,
    ) -> None:
        self._retrieval = retrieval_service
        self._llm = llm_provider
        self._companies = company_repository

    async def run(self, context: AgentContext) -> AgentFinding:
        company = await self._companies.get_by_id(uuid.UUID(context.company_id))
        if company is None:
            raise NotFoundError(f"No company found with id '{context.company_id}'")
        symbol = company.symbol

        package = await self._retrieval.build_context_package(
            symbol, FUNDAMENTAL_ANALYSIS_QUERY, limit=EVIDENCE_LIMIT
        )
        evidence = [
            item for item in package.evidence if item.source_type in RELEVANT_EVIDENCE_TYPES
        ]

        evidence_confidence = compute_evidence_confidence(evidence)
        if evidence_confidence <= EVIDENCE_CONFIDENCE_FLOOR:
            logger.info(
                "fundamental_analysis_insufficient_evidence",
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
    ) -> FundamentalAnalysisResult:
        user_prompt = build_user_prompt(symbol, FUNDAMENTAL_ANALYSIS_QUERY, evidence)
        completion = await self._llm.complete(
            FUNDAMENTAL_ANALYST_SYSTEM_PROMPT,
            user_prompt,
            LLMFundamentalOutput.model_json_schema(),
        )

        try:
            llm_output = LLMFundamentalOutput.model_validate(completion.parsed_json)
        except ValidationError as exc:
            raise LLMResponseParsingError(
                f"LLM response did not match the expected schema: {exc}"
            ) from exc

        strengths, dropped_strengths = drop_unsupported_assessments(
            llm_output.strengths, len(evidence)
        )
        concerns, dropped_concerns = drop_unsupported_assessments(
            llm_output.concerns, len(evidence)
        )

        check_no_investment_advice(
            llm_output.summary,
            llm_output.financial_health_assessment,
            *(assessment.observation for assessment in strengths),
            *(assessment.observation for assessment in concerns),
        )

        citations = resolve_citation_refs(strengths + concerns, evidence)
        confidence_score = compute_confidence_score(evidence_confidence, llm_output.llm_confidence)

        caveats: list[str] = []
        dropped_total = dropped_strengths + dropped_concerns
        if dropped_total:
            caveats.append(
                f"{dropped_total} claim(s) were removed for citing evidence outside the "
                f"provided reference list."
            )
        if not any(item.source_type == EVIDENCE_SOURCE_FINANCIAL_STATEMENT for item in evidence):
            caveats.append("No financial statement evidence was available for this analysis.")

        return FundamentalAnalysisResult(
            company_symbol=symbol,
            summary=llm_output.summary,
            strengths=strengths,
            concerns=concerns,
            financial_health_assessment=llm_output.financial_health_assessment,
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
    ) -> FundamentalAnalysisResult:
        """Deterministic short-circuit -- no LLM call is made at all when
        there isn't enough fundamentals evidence to analyze. Returning an
        explicit "insufficient evidence" result instead of guessing is a
        hard product requirement, not just a quality nicety (see
        FUNDAMENTAL_ANALYST_DESIGN.md §8/§9)."""
        return FundamentalAnalysisResult(
            company_symbol=symbol,
            summary=(
                "Insufficient evidence is available to produce a fundamental "
                "analysis for this company."
            ),
            strengths=[],
            concerns=[],
            financial_health_assessment=(
                "No financial statement evidence was found, so financial health cannot be assessed."
            ),
            evidence_sufficiency="insufficient",
            confidence_score=evidence_confidence,
            citations=[],
            caveats=[
                "No financial statement evidence was found for this company. "
                "Run a financials sync before requesting fundamental analysis."
            ],
            prompt_version=PROMPT_VERSION,
            model_used="none",
            generated_at=datetime.now(UTC),
        )

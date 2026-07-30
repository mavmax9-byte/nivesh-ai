"""Valuation Analyst -- computes a real P/E ratio before reasoning.

Implements `BaseAgent` (agents/base.py). Unlike every other specialist in
this codebase, this agent has two extra dependencies beyond
`RetrievalEngineService`: `FinancialStatementRepository` (to resolve its
highest-relevance `financial_statement` evidence item's id back to the full
statement, for its EPS) and `ResearchDossierRepository` (for the company's
latest known price snapshot) -- see ratios.py for why, and
INVESTMENT_COMMITTEE_DESIGN.md §3a for the confirmed design decision.

The computed P/E, when available, is appended to the evidence list as one
synthetic `computed_ratio` evidence item *before* the LLM prompt is built,
so it is numbered and citable exactly like retrieved evidence. P/B is never
computed (see ratios.py's module docstring for the permanent data gap) --
every finding this agent produces carries a disclosed caveat about it.
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError

from nivesh.ai_agents.agents.base import AgentContext, AgentFinding, BaseAgent
from nivesh.ai_agents.agents.valuation.prompts import (
    PROMPT_VERSION,
    VALUATION_ANALYST_SYSTEM_PROMPT,
    build_user_prompt,
)
from nivesh.ai_agents.agents.valuation.queries import (
    RELEVANT_EVIDENCE_TYPES,
    VALUATION_ANALYSIS_QUERY,
)
from nivesh.ai_agents.agents.valuation.ratios import (
    ComputedRatios,
    compute_price_to_earnings,
)
from nivesh.ai_agents.agents.valuation.schemas import (
    LLMValuationOutput,
    ValuationAnalysisResult,
)
from nivesh.ai_agents.agents.valuation.validation import (
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
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.research.repository import ResearchDossierRepository
from nivesh.retrieval_engine.models import EVIDENCE_SOURCE_FINANCIAL_STATEMENT
from nivesh.retrieval_engine.normalization import EvidenceItem
from nivesh.retrieval_engine.service import RetrievalEngineService

logger = logging.getLogger(__name__)

AGENT_CODE = "valuation_analyst"

EVIDENCE_LIMIT = 30


class ValuationAnalystAgent(BaseAgent):
    agent_code = AGENT_CODE

    def __init__(
        self,
        retrieval_service: RetrievalEngineService,
        llm_provider: LLMProvider,
        company_repository: CompanyRepository,
        statement_repository: FinancialStatementRepository,
        dossier_repository: ResearchDossierRepository,
        shared_evidence: list[EvidenceItem] | None = None,
    ) -> None:
        self._retrieval = retrieval_service
        self._llm = llm_provider
        self._companies = company_repository
        self._statements = statement_repository
        self._dossiers = dossier_repository
        self._shared_evidence = shared_evidence

    async def run(self, context: AgentContext) -> AgentFinding:
        company_id = uuid.UUID(context.company_id)
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise NotFoundError(f"No company found with id '{context.company_id}'")
        symbol = company.symbol

        if self._shared_evidence is None:
            package = await self._retrieval.build_context_package(
                symbol, VALUATION_ANALYSIS_QUERY, limit=EVIDENCE_LIMIT
            )
            pool = list(package.evidence)
        else:
            pool = self._shared_evidence
        evidence = [item for item in pool if item.source_type in RELEVANT_EVIDENCE_TYPES]

        evidence_confidence = compute_evidence_confidence(evidence)
        if evidence_confidence <= EVIDENCE_CONFIDENCE_FLOOR:
            logger.info(
                "valuation_analysis_insufficient_evidence",
                extra={"symbol": symbol, "evidence_count": len(evidence)},
            )
            result = self._insufficient_evidence_result(symbol, evidence_confidence)
        else:
            ratios = await self._compute_ratios(company_id, evidence)
            full_evidence = (
                [*evidence, ratios.evidence_item] if ratios.evidence_item else list(evidence)
            )
            result = await self._analyze(symbol, full_evidence, evidence_confidence, ratios.caveats)

        return AgentFinding(
            agent_code=AGENT_CODE,
            summary=result.summary,
            confidence_score=result.confidence_score,
            evidence_ids=[str(citation.source_id) for citation in result.citations],
            detail=result.model_dump(mode="json"),
        )

    # -- internals -----------------------------------------------------

    async def _compute_ratios(
        self, company_id: uuid.UUID, evidence: list[EvidenceItem]
    ) -> ComputedRatios:
        statement = None
        latest_statement_item = next(
            (item for item in evidence if item.source_type == EVIDENCE_SOURCE_FINANCIAL_STATEMENT),
            None,
        )
        if latest_statement_item is not None:
            statement = await self._statements.get_by_id(latest_statement_item.source_id)

        latest_price = None
        latest_trade_date = None
        dossier = await self._dossiers.get_by_company_id(company_id)
        if dossier is not None:
            version = await self._dossiers.get_latest_version(dossier.id)
            if version is not None and version.snapshot is not None:
                latest_price = version.snapshot.latest_price
                latest_trade_date = version.snapshot.latest_trade_date

        return compute_price_to_earnings(
            statement=statement, latest_price=latest_price, latest_trade_date=latest_trade_date
        )

    async def _analyze(
        self,
        symbol: str,
        evidence: list[EvidenceItem],
        evidence_confidence: float,
        ratio_caveats: list[str],
    ) -> ValuationAnalysisResult:
        user_prompt = build_user_prompt(symbol, VALUATION_ANALYSIS_QUERY, evidence)
        completion = await self._llm.complete(
            VALUATION_ANALYST_SYSTEM_PROMPT,
            user_prompt,
            LLMValuationOutput.model_json_schema(),
        )

        try:
            llm_output = LLMValuationOutput.model_validate(completion.parsed_json)
        except ValidationError as exc:
            raise LLMResponseParsingError(
                f"LLM response did not match the expected schema: {exc}"
            ) from exc

        findings, dropped_findings = drop_unsupported_assessments(
            llm_output.findings, len(evidence)
        )

        check_no_investment_advice(
            llm_output.summary,
            llm_output.valuation_assessment,
            *(assessment.observation for assessment in findings),
        )

        citations = resolve_citation_refs(findings, evidence)
        confidence_score = compute_confidence_score(evidence_confidence, llm_output.llm_confidence)

        caveats = list(ratio_caveats)
        if dropped_findings:
            caveats.append(
                f"{dropped_findings} claim(s) were removed for citing evidence outside the "
                f"provided reference list."
            )

        return ValuationAnalysisResult(
            company_symbol=symbol,
            summary=llm_output.summary,
            findings=findings,
            valuation_assessment=llm_output.valuation_assessment,
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
    ) -> ValuationAnalysisResult:
        return ValuationAnalysisResult(
            company_symbol=symbol,
            summary=(
                "Insufficient evidence is available to produce a valuation analysis for this "
                "company."
            ),
            findings=[],
            valuation_assessment="No financial statement evidence was found, so valuation cannot "
            "be assessed.",
            evidence_sufficiency="insufficient",
            confidence_score=evidence_confidence,
            citations=[],
            caveats=[
                "No financial statement evidence was found for this company. Run a financials "
                "sync before requesting valuation analysis."
            ],
            prompt_version=PROMPT_VERSION,
            model_used="none",
            generated_at=datetime.now(UTC),
        )

"""Investment Committee orchestrator (v1.0).

Fills in what the v0.9 placeholder deferred (per docs/v2
05-Investment-Committee.md and INVESTMENT_COMMITTEE_DESIGN.md): runs every
specialist over one shared evidence pool, synthesizes their findings via
the Committee Chair, gates the result through Compliance, and persists
everything. This class is the actual synthesis/fan-out ENGINE -- it knows
nothing about Celery; it is invoked from `ingestion/tasks.py`'s
`run_investment_committee` task the same way `AIAgentsService` is invoked
from `_generate_fundamental_analysis`. Enqueuing (`POST /reports`) is
handled directly in `router.py`, mirroring `fundamental_router`'s own
"resolve company, `.delay()` the task" shape -- there is no
`request_analysis`-style indirection here to avoid a circular import
between this module and `ingestion/tasks.py`.

**Shared retrieval (§3, confirmed this planning session):** exactly one
`RetrievalEngineService.build_context_package` call per committee run,
with a broad, committee-wide query (`COMMITTEE_EVIDENCE_QUERY`) and a
higher limit (`SHARED_EVIDENCE_LIMIT=60`) than any single specialist needs
alone, since one pool must now carry enough evidence for five specialists'
filters. The resulting pool is injected into every specialist agent via
its `shared_evidence` constructor parameter (§3) -- no specialist performs
its own retrieval when run as part of a committee.

**Quorum (§9, confirmed): Fundamental Analyst must always succeed.** All
five specialists are attempted regardless of each other's outcome (any
subset of the other four may fail without failing the committee run); only
after every specialist has been attempted is quorum checked. A specialist
succeeding with its own "insufficient evidence" result still counts as a
success for quorum purposes -- it is a successful run producing a
low-confidence finding, not a failure.

**Persistence (§10):** this class owns every write for a committee run --
each specialist's own row (via its existing `AIAgentsService.run_analysis`,
completely unchanged), plus the Chair's `investment_committee` row and
Compliance's `compliance_review` row (via `AIAgentsService.persist_finding`,
new in v1.0 -- see service.py). The `investment_committee` row is persisted
even when Compliance rejects it (an auditable record of what was rejected
and why, §10's "disclosed limitation over silent failure" norm) --
`ComplianceRejectedError` is raised only after both rows are durably
written, so the run still fails closed at the Celery task layer.
"""

import logging
import uuid
from dataclasses import dataclass

from nivesh.ai_agents.agents.base import AgentFinding, BaseAgent
from nivesh.ai_agents.agents.fundamental.agent import FundamentalAnalystAgent
from nivesh.ai_agents.agents.news_sentiment.agent import NewsSentimentAnalystAgent
from nivesh.ai_agents.agents.risk.agent import RiskAnalystAgent
from nivesh.ai_agents.agents.technical.agent import TechnicalAnalystAgent
from nivesh.ai_agents.agents.valuation.agent import ValuationAnalystAgent
from nivesh.ai_agents.committee import compliance
from nivesh.ai_agents.committee.chair import CommitteeChair
from nivesh.ai_agents.committee.exceptions import (
    CommitteeQuorumNotMetError,
    ComplianceRejectedError,
)
from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.models import (
    AGENT_CODE_COMPLIANCE_REVIEW,
    AGENT_CODE_FUNDAMENTAL_ANALYST,
    AGENT_CODE_INVESTMENT_COMMITTEE,
    AGENT_CODE_NEWS_SENTIMENT_ANALYST,
    AGENT_CODE_RISK_ANALYST,
    AGENT_CODE_TECHNICAL_ANALYST,
    AGENT_CODE_VALUATION_ANALYST,
    SPECIALIST_AGENT_CODES,
)
from nivesh.ai_agents.providers.base import LLMProvider
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.ai_agents.service import AIAgentsService
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.research.repository import ResearchDossierRepository
from nivesh.retrieval_engine.normalization import EvidenceItem
from nivesh.retrieval_engine.service import RetrievalEngineService

logger = logging.getLogger(__name__)

COMMITTEE_EVIDENCE_QUERY = (
    "financial fundamentals, valuation, technical momentum, news sentiment, and risk factors"
)

# Higher than any single specialist's own EVIDENCE_LIMIT=30 -- one pool now
# has to carry enough evidence for five specialists' independent filters
# (INVESTMENT_COMMITTEE_DESIGN.md §3). A starting guess, not empirically
# tuned, the same caveat every other limit constant in this codebase
# carries.
SHARED_EVIDENCE_LIMIT = 60

_SUFFICIENCY_RANK = {"insufficient": 0, "partial": 1, "sufficient": 2}


@dataclass(frozen=True)
class CommitteeRunResult:
    company_id: uuid.UUID
    symbol: str
    succeeded_specialists: list[str]
    failed_specialists: list[str]
    compliance_approved: bool
    confidence_score: float


class InvestmentCommitteeOrchestrator:
    def __init__(
        self,
        retrieval_service: RetrievalEngineService,
        llm_provider: LLMProvider,
        company_repository: CompanyRepository,
        statement_repository: FinancialStatementRepository,
        dossier_repository: ResearchDossierRepository,
        finding_repository: AgentFindingRepository,
    ) -> None:
        self._retrieval = retrieval_service
        self._llm = llm_provider
        self._companies = company_repository
        self._statements = statement_repository
        self._dossiers = dossier_repository
        self._findings = finding_repository

    async def run(self, symbol: str) -> CommitteeRunResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        package = await self._retrieval.build_context_package(
            symbol, COMMITTEE_EVIDENCE_QUERY, limit=SHARED_EVIDENCE_LIMIT
        )
        shared_evidence = list(package.evidence)

        succeeded, failed = await self._run_specialists(company.id, symbol, shared_evidence)

        if AGENT_CODE_FUNDAMENTAL_ANALYST not in {entry.agent_code for entry in succeeded}:
            logger.error(
                "committee_quorum_not_met",
                extra={"symbol": symbol, "failed_specialists": failed},
            )
            raise CommitteeQuorumNotMetError(
                f"Fundamental Analyst did not succeed for '{symbol}'; no committee decision can "
                f"be produced.",
                details={"failed_specialists": failed},
            )

        chair = CommitteeChair(llm_provider=self._llm)
        decision = await chair.synthesize(symbol, succeeded, failed)
        evidence_sufficiency = _aggregate_evidence_sufficiency(succeeded)

        persistence = AIAgentsService(
            agent=None,
            company_repository=self._companies,
            finding_repository=self._findings,
            dossier_repository=self._dossiers,
        )
        await persistence.persist_finding(
            symbol,
            AgentFinding(
                agent_code=AGENT_CODE_INVESTMENT_COMMITTEE,
                summary=decision.summary,
                confidence_score=decision.confidence_score,
                evidence_ids=[str(citation.source_id) for citation in decision.citations],
                detail={
                    **decision.model_dump(mode="json"),
                    "evidence_sufficiency": evidence_sufficiency,
                },
            ),
        )

        verdict = compliance.review(decision)
        await persistence.persist_finding(
            symbol,
            AgentFinding(
                agent_code=AGENT_CODE_COMPLIANCE_REVIEW,
                summary=(
                    "Committee decision approved for publication."
                    if verdict.approved
                    else "Committee decision rejected: " + "; ".join(verdict.reasons)
                ),
                confidence_score=1.0 if verdict.approved else 0.0,
                evidence_ids=[],
                detail={
                    "approved": verdict.approved,
                    "reasons": verdict.reasons,
                    "evidence_sufficiency": evidence_sufficiency,
                },
            ),
            # Compliance's verdict is an audit record of the *review*, not a
            # new piece of evidence about the company -- §10 says the
            # Chair's own row is the one additional Research Dossier
            # evidence entry, not a second one for Compliance.
            link_to_dossier=False,
        )

        if not verdict.approved:
            raise ComplianceRejectedError(
                f"Compliance rejected the committee decision for '{symbol}'.",
                details={"reasons": verdict.reasons},
            )

        return CommitteeRunResult(
            company_id=company.id,
            symbol=symbol,
            succeeded_specialists=[entry.agent_code for entry in succeeded],
            failed_specialists=failed,
            compliance_approved=verdict.approved,
            confidence_score=decision.confidence_score,
        )

    # -- internals -----------------------------------------------------

    async def _run_specialists(
        self, company_id: uuid.UUID, symbol: str, shared_evidence: list[EvidenceItem]
    ) -> tuple[list[SpecialistFindingInput], list[str]]:
        """Runs every specialist **sequentially**, deliberately, not via
        `asyncio.gather`: every specialist's `AIAgentsService` here shares
        this orchestrator's single `AsyncSession` (via `self._companies`/
        `self._findings`/`self._dossiers`, all bound to the one session the
        Celery task opened -- see `ingestion/tasks.py`'s module docstring on
        why one task always uses exactly one session). A single
        `AsyncSession` is not safe for concurrent use from multiple
        coroutines; running these concurrently would need each specialist
        on its own session, which is a bigger change than this version's
        scope. Five sequential LLM calls is the real latency/cost this
        design accepts for v1.0 -- flagged explicitly, not accidental.
        """
        agents = self._build_specialist_agents(shared_evidence)
        succeeded: list[SpecialistFindingInput] = []
        failed: list[str] = []

        for agent_code in SPECIALIST_AGENT_CODES:
            service = AIAgentsService(
                agent=agents[agent_code],
                company_repository=self._companies,
                finding_repository=self._findings,
                dossier_repository=self._dossiers,
            )
            try:
                await service.run_analysis(symbol)
            except Exception:
                logger.exception(
                    "committee_specialist_failed",
                    extra={"symbol": symbol, "agent_code": agent_code},
                )
                failed.append(agent_code)
                continue

            finding_row = await self._findings.get_latest(company_id, agent_code)
            if finding_row is None:  # pragma: no cover -- defensive, should not happen
                failed.append(agent_code)
                continue
            succeeded.append(
                SpecialistFindingInput(
                    agent_code=agent_code,
                    finding_id=finding_row.id,
                    confidence_score=finding_row.confidence_score,
                    evidence_sufficiency=finding_row.evidence_sufficiency,
                    result_json=finding_row.result_json,
                )
            )

        return succeeded, failed

    def _build_specialist_agents(self, shared_evidence: list[EvidenceItem]) -> dict[str, BaseAgent]:
        return {
            AGENT_CODE_FUNDAMENTAL_ANALYST: FundamentalAnalystAgent(
                retrieval_service=self._retrieval,
                llm_provider=self._llm,
                company_repository=self._companies,
                shared_evidence=shared_evidence,
            ),
            AGENT_CODE_TECHNICAL_ANALYST: TechnicalAnalystAgent(
                retrieval_service=self._retrieval,
                llm_provider=self._llm,
                company_repository=self._companies,
                shared_evidence=shared_evidence,
            ),
            AGENT_CODE_VALUATION_ANALYST: ValuationAnalystAgent(
                retrieval_service=self._retrieval,
                llm_provider=self._llm,
                company_repository=self._companies,
                statement_repository=self._statements,
                dossier_repository=self._dossiers,
                shared_evidence=shared_evidence,
            ),
            AGENT_CODE_NEWS_SENTIMENT_ANALYST: NewsSentimentAnalystAgent(
                retrieval_service=self._retrieval,
                llm_provider=self._llm,
                company_repository=self._companies,
                shared_evidence=shared_evidence,
            ),
            AGENT_CODE_RISK_ANALYST: RiskAnalystAgent(
                retrieval_service=self._retrieval,
                llm_provider=self._llm,
                company_repository=self._companies,
                shared_evidence=shared_evidence,
            ),
        }


def _aggregate_evidence_sufficiency(succeeded: list[SpecialistFindingInput]) -> str:
    """The committee's own evidence_sufficiency is the most conservative
    (lowest) value among contributing specialists -- a committee decision
    is only as well-evidenced as its weakest contributing specialist,
    mirroring the confidence aggregation's own "never let a strong
    specialist paper over a weak one" spirit (§8)."""
    return min(
        (entry.evidence_sufficiency for entry in succeeded),
        key=lambda value: _SUFFICIENCY_RANK.get(value, 0),
    )

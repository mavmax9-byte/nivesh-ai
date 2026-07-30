"""ai_agents service.

Orchestrates one specialist agent's run: resolve the company, invoke the
agent (which itself handles retrieval, LLM reasoning, and every
hallucination-prevention guardrail -- see agents/fundamental/agent.py),
persist the resulting `AgentFinding`, and link it into the Research
Dossier as evidence. This is the same "validate -> normalize -> persist
-> link dossier" shape every ingesting module's service.py already
follows (PROJECT_CONTEXT.md §7) -- the difference from every prior module
is that the "provider" doing the real work here is an LLM-backed
reasoning agent, not a data-ingestion provider, and there is no separate
normalization step since the agent already returns a fully-formed,
guard-validated `AgentFinding`.

A single, discrete `SOURCE_TYPE_AGENT_FINDING` evidence row is attached
per run (`reference_id` = the persisted `AgentFinding`'s own id,
`record_count=1`) -- unlike technical_intelligence/knowledge_layer's
aggregate-per-run rows (many underlying values collapsed into one
range-based row), one agent run produces exactly one finding, so a
discrete, one-row-per-item reference (the same shape
corporate_filings/document_intelligence/news_intelligence use) is the
correct fit here, not an aggregate range.

`persist_finding` (v1.0) factors the persist-and-link half of
`run_analysis` out into its own public method, reused by the Investment
Committee orchestrator for the Committee Chair's and Compliance's own
findings -- neither is produced by a `BaseAgent.run()` call (per
INVESTMENT_COMMITTEE_DESIGN.md §6, neither is a `BaseAgent`), but both are
wrapped into the exact same generic `agents.base.AgentFinding` shape every
specialist already returns, so they persist identically once built. `agent`
is optional for exactly this "persist-only" use: the orchestrator
instantiates this service once per committee run without a concrete
specialist agent behind it, and only ever calls `persist_finding` on that
instance, never `run_analysis`.

`persist_finding` takes `link_to_dossier` (default `True`) because not
every persisted finding should become its own Research Dossier evidence
row: §10 is explicit that "the Chair's run adds exactly one more [evidence
row], on top" of each specialist's own -- Compliance's verdict is an audit
record of the *review*, not a new piece of evidence about the company, so
the orchestrator passes `link_to_dossier=False` for it.
"""

import logging
import uuid
from dataclasses import dataclass

from nivesh.ai_agents.agents.base import AgentContext, AgentFinding, BaseAgent
from nivesh.ai_agents.models import AgentFinding as AgentFindingRow
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.research.models import SOURCE_TYPE_AGENT_FINDING
from nivesh.research.repository import ResearchDossierRepository

logger = logging.getLogger(__name__)

PROVIDER_SOURCE_TABLE = "agent_findings"
EVENT_TYPE_FINDING_GENERATED = "agent_finding_generated"


@dataclass(frozen=True)
class AgentAnalysisResult:
    company_id: uuid.UUID
    symbol: str
    agent_code: str
    confidence_score: float
    evidence_sufficiency: str


class AIAgentsService:
    def __init__(
        self,
        agent: BaseAgent | None,
        company_repository: CompanyRepository,
        finding_repository: AgentFindingRepository,
        dossier_repository: ResearchDossierRepository,
    ) -> None:
        self._agent = agent
        self._companies = company_repository
        self._findings = finding_repository
        self._dossiers = dossier_repository

    async def run_analysis(self, symbol: str) -> AgentAnalysisResult:
        if self._agent is None:
            raise NotImplementedError(
                "run_analysis requires a concrete agent; this service instance was constructed "
                "in persist-only mode -- use persist_finding instead."
            )
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        context = AgentContext(company_id=str(company.id), trigger_type="manual")
        finding = await self._agent.run(context)
        return await self._persist(company.id, company.symbol, finding, link_to_dossier=True)

    async def persist_finding(
        self, symbol: str, finding: AgentFinding, *, link_to_dossier: bool = True
    ) -> AgentAnalysisResult:
        """Persists an already-produced `AgentFinding` and, by default,
        links it into the Research Dossier -- the second half of
        `run_analysis`, factored out for the Investment Committee
        orchestrator's Chair/Compliance findings (see module docstring for
        why Compliance passes `link_to_dossier=False`)."""
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._persist(
            company.id, company.symbol, finding, link_to_dossier=link_to_dossier
        )

    async def get_latest_finding(self, symbol: str) -> AgentFindingRow | None:
        if self._agent is None:
            raise NotImplementedError(
                "get_latest_finding requires a concrete agent; this service instance was "
                "constructed in persist-only mode."
            )
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._findings.get_latest(company.id, self._agent.agent_code)

    # -- internals -----------------------------------------------------

    async def _persist(
        self,
        company_id: uuid.UUID,
        symbol: str,
        finding: AgentFinding,
        *,
        link_to_dossier: bool,
    ) -> AgentAnalysisResult:
        detail = finding.detail or {}
        await self._findings.upsert(
            company_id=company_id,
            agent_code=finding.agent_code,
            result_json=detail,
            prompt_version=detail.get("prompt_version", ""),
            model_used=detail.get("model_used", ""),
            confidence_score=finding.confidence_score,
            evidence_sufficiency=detail.get("evidence_sufficiency", "insufficient"),
        )
        if link_to_dossier:
            await self._link_to_research_dossier(company_id, symbol, finding.agent_code)

        return AgentAnalysisResult(
            company_id=company_id,
            symbol=symbol,
            agent_code=finding.agent_code,
            confidence_score=finding.confidence_score,
            evidence_sufficiency=detail.get("evidence_sufficiency", "insufficient"),
        )

    async def _link_to_research_dossier(
        self, company_id: uuid.UUID, symbol: str, agent_code: str
    ) -> None:
        """Records a newly persisted finding as one discrete Research
        Dossier evidence row.

        Sources are attached to the current research version if one
        already exists; version numbering itself stays owned by
        ResearchPipelineService, so this never creates or bumps a
        research version -- only adds evidence to one that already
        exists.
        """
        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "agent_finding_generated_before_research_version",
                extra={"symbol": symbol, "agent_code": agent_code},
            )
            return

        finding = await self._findings.get_latest(company_id, agent_code)
        if finding is None:
            return

        source_rows = [
            {
                "dossier_id": dossier.id,
                "version_id": latest_version.id,
                "source_type": SOURCE_TYPE_AGENT_FINDING,
                "reference_table": PROVIDER_SOURCE_TABLE,
                "reference_id": finding.id,
                "range_start": None,
                "range_end": None,
                "record_count": 1,
            }
        ]
        await self._dossiers.bulk_create_sources(source_rows)
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_FINDING_GENERATED,
            description=f"'{agent_code}' analysis generated for '{symbol}'.",
            version_id=latest_version.id,
        )
        await self._findings.commit()

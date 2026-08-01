"""Portfolio Planner service.

Implements INVESTMENT_PLANNER_DESIGN.md's generation workflow (§3) as a
**deterministic aggregation/ranking/allocation layer over already-
guardrailed Investment Committee output** (§0) -- this module makes no
LLM calls of its own. It reuses, unchanged:

- `CompanyRepository`/`FinancialStatementRepository` for universe
  selection (§4);
- `InvestmentCommitteeOrchestrator` (`ai_agents/orchestrator.py`) to
  generate a fresh committee report for any candidate that needs one --
  the exact same class `ingestion/tasks.py::_run_investment_committee`
  already uses, not a second invocation path;
- `AgentFindingRepository.get_latest` to read each candidate's existing
  `investment_committee`/`compliance_review` rows.

Ranking (§5), allocation (§6), and explanation generation (§8) are pure
Python over that already-cited, already-compliance-gated data -- no new
guardrail surface is introduced.

**Identity-map caution, carried forward from v1.2** (see
`ai_agents/repository.py::AgentFindingRepository.get_latest`'s own
docstring): this service reads a candidate's `investment_committee`
row *before* possibly regenerating it via the orchestrator, then reads
it again afterward. Without expiring the session between those two
reads, the second read -- and, more importantly, the orchestrator's own
*internal* post-upsert read inside `_link_to_research_dossier` -- would
return a stale, pre-regeneration cached object. `_ensure_fresh_report`
calls `session.expire_all()` before invoking the orchestrator specifically
to prevent this.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.ai_agents.committee.exceptions import (
    CommitteeQuorumNotMetError,
    ComplianceRejectedError,
)
from nivesh.ai_agents.models import AGENT_CODE_COMPLIANCE_REVIEW, AGENT_CODE_INVESTMENT_COMMITTEE
from nivesh.ai_agents.orchestrator import InvestmentCommitteeOrchestrator
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.companies.models import Company
from nivesh.companies.repository import CompanyRepository
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.market_universe.repository import UniverseConstituentRepository
from nivesh.portfolio_planner.models import PlannedPortfolio
from nivesh.portfolio_planner.repository import PlannedPortfolioRepository

logger = logging.getLogger(__name__)

# Documented starting guesses, not empirically tuned -- the same caveat
# every other scoring/threshold constant in this codebase carries
# (RECENCY_HALF_LIFE_DAYS, SHARED_EVIDENCE_LIMIT, etc.). Revisit once
# real portfolio-generation usage exists to tune against.
UNIVERSE_TIER1_LIMIT = 500
UNIVERSE_TIER2_CAP = 25
COMMITTEE_FRESHNESS = timedelta(days=7)
MAX_HOLDINGS = 15

_SUFFICIENCY_SCORE = {"sufficient": 1.0, "partial": 0.6, "insufficient": 0.2}
_SUFFICIENCY_RANK = {"insufficient": 0, "partial": 1, "sufficient": 2}

_PROFILE_WEIGHTS = {
    "conservative": {"confidence": 0.35, "evidence": 0.30, "stance": 0.15, "disagreement": 0.20},
    "balanced": {"confidence": 0.30, "evidence": 0.20, "stance": 0.30, "disagreement": 0.20},
    "growth": {"confidence": 0.25, "evidence": 0.15, "stance": 0.45, "disagreement": 0.15},
}
_MAX_POSITION_WEIGHT = {"conservative": 0.15, "balanced": 0.20, "growth": 0.25}
_MAX_SECTOR_WEIGHT = {"conservative": 0.30, "balanced": 0.35, "growth": 0.40}


@dataclass
class ScoredCandidate:
    company: Company
    decision: dict
    rank_score: float
    confidence_score: float
    evidence_sufficiency: str


class PortfolioPlannerService:
    def __init__(
        self,
        session: AsyncSession,
        company_repository: CompanyRepository,
        statement_repository: FinancialStatementRepository,
        finding_repository: AgentFindingRepository,
        portfolio_repository: PlannedPortfolioRepository,
        orchestrator: InvestmentCommitteeOrchestrator,
        universe_repository: UniverseConstituentRepository | None = None,
    ) -> None:
        self._session = session
        self._companies = company_repository
        self._statements = statement_repository
        self._findings = finding_repository
        self._portfolios = portfolio_repository
        self._orchestrator = orchestrator
        # Optional (v1.4, PROJECT_CONTEXT.md §13 point 1g): when given,
        # Tier 2's shortlist prefers market_universe's deterministically
        # screened-in candidates over the plain alphabetical fallback --
        # see _select_universe. Defaults to None so any existing caller
        # (and every pre-v1.4 test) keeps the exact v1.3 behavior.
        self._universe = universe_repository

    async def generate(self, portfolio_id: uuid.UUID) -> None:
        portfolio = await self._portfolios.get_by_id(portfolio_id)
        if portfolio is None:  # pragma: no cover -- defensive, should not happen
            logger.error("planner_portfolio_not_found", extra={"portfolio_id": str(portfolio_id)})
            return

        try:
            await self._generate(portfolio)
        except Exception as exc:
            logger.exception("planner_generation_failed", extra={"portfolio_id": str(portfolio_id)})
            await self._portfolios.mark_failed(portfolio, reason=str(exc)[:500])

    # -- internals -------------------------------------------------------

    async def _generate(self, portfolio: PlannedPortfolio) -> None:
        universe = await self._select_universe(portfolio.sector_exclusions)
        if not universe:
            await self._portfolios.mark_failed(
                portfolio,
                reason=(
                    "No companies in the current research universe matched the requested "
                    "sector exclusions, or none have sufficient financial data to analyze."
                ),
            )
            return

        scored: list[ScoredCandidate] = []
        for company in universe:
            candidate = await self._score_one(company, portfolio.risk_profile)
            if candidate is not None:
                scored.append(candidate)

        if not scored:
            await self._portfolios.mark_failed(
                portfolio,
                reason=(
                    "None of the companies in the current research universe currently have an "
                    "approved Investment Committee report (quorum not met or compliance "
                    "rejected the draft)."
                ),
            )
            return

        caveats: list[str] = []
        filtered = self._apply_risk_filter(scored, portfolio.risk_profile)
        if not filtered:
            filtered = scored
            caveats.append(
                "Strict risk-profile filtering excluded every candidate in the current "
                "universe; showing the best available research instead."
            )

        filtered.sort(key=lambda c: c.rank_score, reverse=True)
        selected = filtered[:MAX_HOLDINGS]

        weights, unallocated_weight = self._allocate(selected, portfolio.risk_profile)
        capital = float(portfolio.capital)

        for candidate in selected:
            weight = weights[candidate.company.id]
            amount = round(capital * weight, 2)
            was_capped = weight < candidate.rank_score / sum(c.rank_score for c in selected)
            decision = candidate.decision
            citations = decision.get("citations") or []
            top_citation = citations[0] if citations else None
            await self._portfolios.add_holding(
                portfolio.id,
                {
                    "company_id": candidate.company.id,
                    "symbol": candidate.company.symbol,
                    "company_name": candidate.company.name,
                    "sector": candidate.company.sector,
                    "allocated_amount": amount,
                    "allocated_weight": weight,
                    "rank_score": candidate.rank_score,
                    "confidence_score": candidate.confidence_score,
                    "evidence_sufficiency": candidate.evidence_sufficiency,
                    "thesis": _thesis(decision),
                    "weight_rationale": _weight_rationale(
                        weight, amount, was_capped, _MAX_POSITION_WEIGHT[portfolio.risk_profile]
                    ),
                    "top_citation_title": top_citation.get("title") if top_citation else None,
                    "top_citation_source_type": (
                        top_citation.get("source_type") if top_citation else None
                    ),
                },
            )

        unallocated_amount = round(capital * unallocated_weight, 2)
        if unallocated_amount > 0.01 * capital:
            caveats.append(
                f"₹{unallocated_amount:,.0f} could not be allocated within this risk "
                f"profile's diversification limits given the size of the current research "
                f"universe."
            )
        if len(universe) < MAX_HOLDINGS:
            caveats.append(
                f"Only {len(universe)} companies are covered by real-time research in this "
                f"environment; a production deployment would screen a much larger universe."
            )

        allocated_weight_sum = sum(weights.values()) or 1.0
        agg_confidence = (
            sum(c.confidence_score * weights[c.company.id] for c in selected) / allocated_weight_sum
        )
        agg_sufficiency = min(
            (c.evidence_sufficiency for c in selected),
            key=lambda s: _SUFFICIENCY_RANK.get(s, 0),
        )

        await self._portfolios.mark_ready(
            portfolio,
            summary=_build_summary(selected, portfolio.risk_profile, len(universe)),
            caveats=caveats,
            unallocated_amount=unallocated_amount,
            confidence_score=agg_confidence,
            evidence_sufficiency=agg_sufficiency,
            universe_size=len(universe),
        )

    async def _select_universe(self, sector_exclusions: list[str]) -> list[Company]:
        """Two-tier funnel (INVESTMENT_PLANNER_DESIGN.md §4): a full
        committee report costs 5-6 real LLM calls, so the full company
        table cannot be screened that way. Tier 1 (free): active,
        sector-permitted, has at least one financial statement (mirrors
        Fundamental Analyst's own quorum requirement, so candidates
        destined to fail quorum are never even attempted). Tier 2 (free):
        cap the shortlist size before any expensive Tier 3 generation --
        when a `market_universe` (v1.4) screening score exists for a
        candidate, it ranks ahead of unscored candidates (deterministic
        evidence-completeness ranking, see market_universe/service.py),
        so the strongest, already-ingested-and-screened companies are the
        ones this cap actually keeps; symbol order is the tie-break, and
        the sole fallback when no `universe_repository` was given at all
        (unchanged v1.3 behavior). Must behave correctly for an
        arbitrarily small candidate pool -- this sandbox's own real data
        is exactly that case."""
        companies = await self._companies.list(limit=UNIVERSE_TIER1_LIMIT)
        exclusions = {s.strip().lower() for s in sector_exclusions}
        tier1 = [c for c in companies if (c.sector or "").strip().lower() not in exclusions]

        survivors = [c for c in tier1 if await self._statements.exists_for_company(c.id)]

        scores: dict[uuid.UUID, float] = {}
        if self._universe is not None and survivors:
            scores = await self._universe.get_screening_scores([c.id for c in survivors])
        survivors.sort(key=lambda c: (-scores.get(c.id, -1.0), c.symbol))
        return survivors[:UNIVERSE_TIER2_CAP]

    async def _score_one(self, company: Company, risk_profile: str) -> ScoredCandidate | None:
        decision = await self._ensure_fresh_report(company)
        if decision is None:
            return None

        findings = decision.get("findings") or []
        positive = sum(1 for f in findings if f.get("stance") == "positive")
        negative = sum(1 for f in findings if f.get("stance") == "negative")
        total = len(findings) or 1
        stance_component = ((positive - negative) / total + 1) / 2

        evidence_sufficiency = decision.get("evidence_sufficiency", "insufficient")
        evidence_component = _SUFFICIENCY_SCORE.get(evidence_sufficiency, 0.2)

        disagreement_count = len(decision.get("disagreements") or [])
        disagreement_component = max(0.0, 1 - min(1.0, disagreement_count * 0.15))

        confidence_component = float(decision.get("confidence_score", 0.0))

        weights = _PROFILE_WEIGHTS[risk_profile]
        rank_score = (
            weights["confidence"] * confidence_component
            + weights["evidence"] * evidence_component
            + weights["stance"] * stance_component
            + weights["disagreement"] * disagreement_component
        )
        return ScoredCandidate(
            company=company,
            decision=decision,
            rank_score=rank_score,
            confidence_score=confidence_component,
            evidence_sufficiency=evidence_sufficiency,
        )

    async def _ensure_fresh_report(self, company: Company) -> dict | None:
        decision_row = await self._findings.get_latest(company.id, AGENT_CODE_INVESTMENT_COMMITTEE)
        compliance_row = await self._findings.get_latest(company.id, AGENT_CODE_COMPLIANCE_REVIEW)

        is_fresh = decision_row is not None and (
            datetime.now(UTC) - decision_row.updated_at.astimezone(UTC) < COMMITTEE_FRESHNESS
        )
        is_approved = compliance_row is not None and bool(
            compliance_row.result_json.get("approved", False)
        )

        if not (is_fresh and is_approved):
            # See module docstring: must expire before the orchestrator
            # runs, not just before our own next read, so its own
            # internal post-upsert read isn't fed a stale cached object.
            self._session.expire_all()
            try:
                await self._orchestrator.run(company.symbol)
            except (CommitteeQuorumNotMetError, ComplianceRejectedError) as exc:
                logger.info(
                    "planner_candidate_excluded",
                    extra={"symbol": company.symbol, "reason": exc.error_code},
                )
                return None
            except Exception:
                logger.exception(
                    "planner_candidate_generation_failed", extra={"symbol": company.symbol}
                )
                return None
            decision_row = await self._findings.get_latest(
                company.id, AGENT_CODE_INVESTMENT_COMMITTEE
            )
            compliance_row = await self._findings.get_latest(
                company.id, AGENT_CODE_COMPLIANCE_REVIEW
            )

        if decision_row is None or compliance_row is None:
            return None
        if not compliance_row.result_json.get("approved", False):
            return None
        return decision_row.result_json

    def _apply_risk_filter(
        self, scored: list[ScoredCandidate], risk_profile: str
    ) -> list[ScoredCandidate]:
        if risk_profile != "conservative":
            return scored
        return [c for c in scored if c.evidence_sufficiency != "insufficient"]

    def _allocate(
        self, selected: list[ScoredCandidate], risk_profile: str
    ) -> tuple[dict[uuid.UUID, float], float]:
        """Score-weighted allocation within per-position and per-sector
        caps (INVESTMENT_PLANNER_DESIGN.md §6). Deliberately does not
        force 100% deployment: if diversification limits can't be met by
        the available universe (a single-candidate universe, the common
        case in this sandbox's own real data, is the extreme version of
        this), the remainder is left honestly unallocated rather than
        concentrated into one name past its cap."""
        if not selected:
            return {}, 1.0

        position_cap = _MAX_POSITION_WEIGHT[risk_profile]
        sector_cap = _MAX_SECTOR_WEIGHT[risk_profile]

        total_score = sum(c.rank_score for c in selected) or 1.0
        weights = {c.company.id: min(c.rank_score / total_score, position_cap) for c in selected}

        sector_totals: dict[str, float] = {}
        for c in selected:
            sector = c.company.sector or "Unclassified"
            sector_totals[sector] = sector_totals.get(sector, 0.0) + weights[c.company.id]
        for c in selected:
            sector = c.company.sector or "Unclassified"
            sector_total = sector_totals[sector]
            if sector_total > sector_cap:
                weights[c.company.id] *= sector_cap / sector_total

        unallocated_weight = max(0.0, 1.0 - sum(weights.values()))
        return weights, unallocated_weight


def _thesis(decision: dict) -> str:
    summary = (decision.get("summary") or "").strip()
    if len(summary) > 240:
        summary = summary[:237].rsplit(" ", 1)[0] + "..."
    return summary or "No summary available for this company's committee report."


def _weight_rationale(weight: float, amount: float, was_capped: bool, position_cap: float) -> str:
    text = (
        f"Allocated {weight:.0%} (₹{amount:,.0f}) based on this company's composite research score."
    )
    if was_capped:
        text += (
            f" Capped at the {position_cap:.0%} single-position diversification "
            f"limit for this risk profile."
        )
    return text


def _build_summary(selected: list[ScoredCandidate], risk_profile: str, universe_size: int) -> str:
    n = len(selected)
    sectors = sorted({c.company.sector for c in selected if c.company.sector})
    sector_text = ", ".join(sectors) if sectors else "a mix of sectors"
    return (
        f"This illustrative allocation spans {n} holding{'s' if n != 1 else ''} in "
        f"{sector_text}, selected from {universe_size} companies currently covered by "
        f"real-time research, weighted toward higher-confidence findings for a "
        f"{risk_profile} risk profile."
    )

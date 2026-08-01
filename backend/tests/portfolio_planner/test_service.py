import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nivesh.ai_agents.committee.exceptions import CommitteeQuorumNotMetError
from nivesh.portfolio_planner.service import PortfolioPlannerService, ScoredCandidate


def _company(symbol: str = "TCS", sector: str | None = "Technology"):
    company = AsyncMock()
    company.id = uuid.uuid4()
    company.symbol = symbol
    company.name = f"{symbol} Limited"
    company.sector = sector
    return company


def _decision(
    *,
    confidence_score: float = 0.7,
    evidence_sufficiency: str = "sufficient",
    stances: list[str] | None = None,
    disagreements: int = 0,
    citations: list[dict] | None = None,
    summary: str = "Solid fundamentals and stable growth.",
) -> dict:
    stances = stances if stances is not None else ["positive", "positive"]
    return {
        "summary": summary,
        "confidence_score": confidence_score,
        "evidence_sufficiency": evidence_sufficiency,
        "findings": [
            {"stance": s, "theme": "x", "observation": "y", "citation_refs": [1]} for s in stances
        ],
        "disagreements": [{"topic": "t", "positions": []} for _ in range(disagreements)],
        "citations": citations
        or [{"title": "Quarterly statement", "source_type": "financial_statement"}],
    }


def _session() -> AsyncMock:
    # `AsyncSession.expire_all` is a real, synchronous method (no I/O,
    # pure Python-side state) even though the surrounding class is async
    # -- a blanket AsyncMock() would wrap it as an awaitable too and mask
    # the service's real (correct) unawaited, synchronous call as an
    # "unawaited coroutine" warning.
    session = AsyncMock()
    session.expire_all = MagicMock()
    return session


def _make_service(**overrides) -> PortfolioPlannerService:
    defaults = dict(
        session=_session(),
        company_repository=AsyncMock(),
        statement_repository=AsyncMock(),
        finding_repository=AsyncMock(),
        portfolio_repository=AsyncMock(),
        orchestrator=AsyncMock(),
    )
    defaults.update(overrides)
    return PortfolioPlannerService(**defaults)


class TestScoreOne:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_approved_report_exists(self):
        service = _make_service()
        service._ensure_fresh_report = AsyncMock(return_value=None)

        result = await service._score_one(_company(), "balanced")

        assert result is None

    @pytest.mark.asyncio
    async def test_higher_confidence_and_sufficiency_score_higher(self):
        service = _make_service()
        strong = _decision(confidence_score=0.9, evidence_sufficiency="sufficient")
        weak = _decision(confidence_score=0.2, evidence_sufficiency="insufficient")
        service._ensure_fresh_report = AsyncMock(side_effect=[strong, weak])

        strong_candidate = await service._score_one(_company("STRONG"), "balanced")
        weak_candidate = await service._score_one(_company("WEAK"), "balanced")

        assert strong_candidate is not None and weak_candidate is not None
        assert strong_candidate.rank_score > weak_candidate.rank_score

    @pytest.mark.asyncio
    async def test_disagreements_reduce_rank_score(self):
        service = _make_service()
        calm = _decision(disagreements=0)
        contentious = _decision(disagreements=3)
        service._ensure_fresh_report = AsyncMock(side_effect=[calm, contentious])

        calm_candidate = await service._score_one(_company("CALM"), "balanced")
        contentious_candidate = await service._score_one(_company("LOUD"), "balanced")

        assert calm_candidate is not None and contentious_candidate is not None
        assert calm_candidate.rank_score > contentious_candidate.rank_score

    @pytest.mark.asyncio
    async def test_negative_stances_score_lower_than_positive(self):
        service = _make_service()
        positive = _decision(stances=["positive", "positive"])
        negative = _decision(stances=["negative", "negative"])
        service._ensure_fresh_report = AsyncMock(side_effect=[positive, negative])

        positive_candidate = await service._score_one(_company("UP"), "growth")
        negative_candidate = await service._score_one(_company("DOWN"), "growth")

        assert positive_candidate is not None and negative_candidate is not None
        assert positive_candidate.rank_score > negative_candidate.rank_score


class TestApplyRiskFilter:
    def test_conservative_drops_insufficient_evidence_candidates(self):
        service = _make_service()
        good = ScoredCandidate(_company("GOOD"), _decision(), 0.8, 0.8, "sufficient")
        thin = ScoredCandidate(_company("THIN"), _decision(), 0.3, 0.1, "insufficient")

        result = service._apply_risk_filter([good, thin], "conservative")

        assert result == [good]

    def test_growth_profile_keeps_everyone(self):
        service = _make_service()
        good = ScoredCandidate(_company("GOOD"), _decision(), 0.8, 0.8, "sufficient")
        thin = ScoredCandidate(_company("THIN"), _decision(), 0.3, 0.1, "insufficient")

        result = service._apply_risk_filter([good, thin], "growth")

        assert result == [good, thin]


class TestAllocate:
    def test_single_candidate_is_capped_and_leaves_residual(self):
        """The real, exercised case in this project's own dev sandbox
        (exactly one real company with full data) -- diversification caps
        must leave an honest unallocated residual, never force 100% into
        one name past its cap (INVESTMENT_PLANNER_DESIGN.md §6)."""
        service = _make_service()
        only = ScoredCandidate(
            _company("ONLY"),
            _decision(),
            rank_score=0.8,
            confidence_score=0.8,
            evidence_sufficiency="sufficient",
        )

        weights, unallocated = service._allocate([only], "balanced")

        assert weights[only.company.id] == pytest.approx(0.20)
        assert unallocated == pytest.approx(0.80)

    def test_two_candidates_same_sector_respect_sector_cap(self):
        service = _make_service()
        a = ScoredCandidate(_company("A"), _decision(), 0.9, 0.9, "sufficient")
        b = ScoredCandidate(_company("B"), _decision(), 0.9, 0.9, "sufficient")

        weights, _ = service._allocate([a, b], "balanced")

        sector_total = weights[a.company.id] + weights[b.company.id]
        assert sector_total <= 0.35 + 1e-9

    def test_different_sectors_are_not_cross_capped(self):
        service = _make_service()
        tech = ScoredCandidate(
            _company("A", sector="Technology"), _decision(), 0.5, 0.5, "sufficient"
        )
        energy = ScoredCandidate(
            _company("B", sector="Energy"), _decision(), 0.5, 0.5, "sufficient"
        )

        weights, unallocated = service._allocate([tech, energy], "growth")

        assert weights[tech.company.id] == pytest.approx(0.25)
        assert weights[energy.company.id] == pytest.approx(0.25)
        assert unallocated == pytest.approx(0.50)

    def test_empty_selection_is_fully_unallocated(self):
        service = _make_service()
        weights, unallocated = service._allocate([], "balanced")
        assert weights == {}
        assert unallocated == 1.0


class TestEnsureFreshReport:
    @pytest.mark.asyncio
    async def test_fresh_approved_report_skips_regeneration(self):
        from datetime import UTC, datetime

        finding_repository = AsyncMock()
        decision_row = AsyncMock()
        decision_row.result_json = _decision()
        decision_row.updated_at = datetime.now(UTC)
        compliance_row = AsyncMock()
        compliance_row.result_json = {"approved": True}
        finding_repository.get_latest.side_effect = [decision_row, compliance_row]

        orchestrator = AsyncMock()
        service = _make_service(finding_repository=finding_repository, orchestrator=orchestrator)

        result = await service._ensure_fresh_report(_company())

        orchestrator.run.assert_not_called()
        assert result == decision_row.result_json

    @pytest.mark.asyncio
    async def test_missing_report_triggers_regeneration_and_expires_session(self):
        finding_repository = AsyncMock()
        fresh_decision = AsyncMock()
        fresh_decision.result_json = _decision()
        fresh_compliance = AsyncMock()
        fresh_compliance.result_json = {"approved": True}
        # First pair (freshness check): nothing exists yet. Second pair
        # (post-regeneration re-read): the freshly generated report.
        finding_repository.get_latest.side_effect = [None, None, fresh_decision, fresh_compliance]

        session = _session()
        orchestrator = AsyncMock()
        service = _make_service(
            session=session, finding_repository=finding_repository, orchestrator=orchestrator
        )

        result = await service._ensure_fresh_report(_company())

        orchestrator.run.assert_called_once()
        session.expire_all.assert_called_once()
        assert result == fresh_decision.result_json

    @pytest.mark.asyncio
    async def test_quorum_not_met_excludes_candidate_without_raising(self):
        finding_repository = AsyncMock()
        finding_repository.get_latest.side_effect = [None, None]
        orchestrator = AsyncMock()
        orchestrator.run.side_effect = CommitteeQuorumNotMetError("no quorum")
        service = _make_service(finding_repository=finding_repository, orchestrator=orchestrator)

        result = await service._ensure_fresh_report(_company())

        assert result is None

    @pytest.mark.asyncio
    async def test_rejected_compliance_triggers_regeneration_and_stays_excluded_if_still_rejected(
        self,
    ):
        """An existing-but-rejected report is not just skipped -- the
        service attempts a fresh regeneration (a prior rejection may have
        been for stale evidence). If it's still rejected afterward, the
        candidate is excluded."""
        from datetime import UTC, datetime

        finding_repository = AsyncMock()
        stale_decision = AsyncMock()
        stale_decision.result_json = _decision()
        stale_decision.updated_at = datetime.now(UTC)
        rejected_compliance = AsyncMock()
        rejected_compliance.result_json = {"approved": False, "reasons": ["advice language"]}
        fresh_decision = AsyncMock()
        fresh_decision.result_json = _decision()
        still_rejected_compliance = AsyncMock()
        still_rejected_compliance.result_json = {"approved": False, "reasons": ["advice language"]}
        finding_repository.get_latest.side_effect = [
            stale_decision,
            rejected_compliance,
            fresh_decision,
            still_rejected_compliance,
        ]
        orchestrator = AsyncMock()
        service = _make_service(finding_repository=finding_repository, orchestrator=orchestrator)

        result = await service._ensure_fresh_report(_company())

        orchestrator.run.assert_called_once()
        assert result is None


class TestSelectUniverse:
    @pytest.mark.asyncio
    async def test_falls_back_to_alphabetical_when_no_universe_repository_given(self):
        company_repository = AsyncMock()
        company_repository.list.return_value = [_company("ZETA"), _company("ALPHA")]
        statement_repository = AsyncMock()
        statement_repository.exists_for_company.return_value = True

        service = _make_service(
            company_repository=company_repository, statement_repository=statement_repository
        )
        assert service._universe is None

        result = await service._select_universe([])

        assert [c.symbol for c in result] == ["ALPHA", "ZETA"]

    @pytest.mark.asyncio
    async def test_prefers_higher_screening_score_over_alphabetical_order(self):
        """v1.4: market_universe's screening score, when available, ranks
        a candidate ahead of plain alphabetical order -- ZETA has a lower
        symbol but the stronger (higher) screening score, so it should be
        selected first."""
        zeta = _company("ZETA")
        alpha = _company("ALPHA")
        company_repository = AsyncMock()
        company_repository.list.return_value = [zeta, alpha]
        statement_repository = AsyncMock()
        statement_repository.exists_for_company.return_value = True
        universe_repository = AsyncMock()
        universe_repository.get_screening_scores.return_value = {
            zeta.id: 0.9,
            alpha.id: 0.2,
        }

        service = _make_service(
            company_repository=company_repository,
            statement_repository=statement_repository,
            universe_repository=universe_repository,
        )

        result = await service._select_universe([])

        assert [c.symbol for c in result] == ["ZETA", "ALPHA"]

    @pytest.mark.asyncio
    async def test_unscored_candidates_sort_after_scored_ones(self):
        scored = _company("ZETA")
        unscored = _company("ALPHA")
        company_repository = AsyncMock()
        company_repository.list.return_value = [unscored, scored]
        statement_repository = AsyncMock()
        statement_repository.exists_for_company.return_value = True
        universe_repository = AsyncMock()
        universe_repository.get_screening_scores.return_value = {scored.id: 0.5}

        service = _make_service(
            company_repository=company_repository,
            statement_repository=statement_repository,
            universe_repository=universe_repository,
        )

        result = await service._select_universe([])

        assert [c.symbol for c in result] == ["ZETA", "ALPHA"]


class TestGenerateEndToEnd:
    @pytest.mark.asyncio
    async def test_empty_universe_marks_portfolio_failed(self):
        portfolio_repository = AsyncMock()
        portfolio = AsyncMock()
        portfolio.id = uuid.uuid4()
        portfolio.sector_exclusions = []
        portfolio_repository.get_by_id.return_value = portfolio

        company_repository = AsyncMock()
        company_repository.list.return_value = []

        service = _make_service(
            company_repository=company_repository, portfolio_repository=portfolio_repository
        )

        await service.generate(portfolio.id)

        portfolio_repository.mark_failed.assert_called_once()
        portfolio_repository.mark_ready.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_eligible_candidate_produces_a_ready_portfolio_with_one_holding(self):
        portfolio_repository = AsyncMock()
        portfolio = AsyncMock()
        portfolio.id = uuid.uuid4()
        portfolio.capital = 100000.0
        portfolio.risk_profile = "balanced"
        portfolio.sector_exclusions = []
        portfolio_repository.get_by_id.return_value = portfolio

        company = _company("TCS")
        company_repository = AsyncMock()
        company_repository.list.return_value = [company]

        statement_repository = AsyncMock()
        statement_repository.exists_for_company.return_value = True

        service = _make_service(
            company_repository=company_repository,
            statement_repository=statement_repository,
            portfolio_repository=portfolio_repository,
        )
        service._ensure_fresh_report = AsyncMock(return_value=_decision())

        await service.generate(portfolio.id)

        portfolio_repository.mark_ready.assert_called_once()
        assert portfolio_repository.add_holding.call_count == 1
        _, holding_kwargs_call = portfolio_repository.add_holding.call_args
        added_portfolio_id, added_data = portfolio_repository.add_holding.call_args[0]
        assert added_portfolio_id == portfolio.id
        assert added_data["symbol"] == "TCS"
        assert added_data["allocated_weight"] == pytest.approx(0.20)

    @pytest.mark.asyncio
    async def test_exception_during_generation_marks_portfolio_failed_not_raised(self):
        portfolio_repository = AsyncMock()
        portfolio = AsyncMock()
        portfolio.id = uuid.uuid4()
        portfolio_repository.get_by_id.return_value = portfolio

        company_repository = AsyncMock()
        company_repository.list.side_effect = RuntimeError("db exploded")

        service = _make_service(
            company_repository=company_repository, portfolio_repository=portfolio_repository
        )

        await service.generate(portfolio.id)  # must not raise

        portfolio_repository.mark_failed.assert_called_once()
        args, kwargs = portfolio_repository.mark_failed.call_args
        assert "db exploded" in kwargs.get("reason", args[1] if len(args) > 1 else "")

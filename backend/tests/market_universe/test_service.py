import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from nivesh.market_universe.models import STATUS_READY, UniverseConstituent
from nivesh.market_universe.service import (
    COMMITTEE_FRESHNESS_DAYS,
    MarketUniverseService,
    ScreeningComponents,
)


def _make_service(**overrides) -> MarketUniverseService:
    statement_repository = AsyncMock()
    statement_repository.exists_for_company.return_value = True
    defaults = dict(
        session=AsyncMock(),
        universe_repository=AsyncMock(),
        company_repository=AsyncMock(),
        exchange_repository=AsyncMock(),
        ohlcv_repository=AsyncMock(),
        indicator_repository=AsyncMock(),
        statement_repository=statement_repository,
        category_repository=AsyncMock(),
        source_repository=AsyncMock(),
        filing_repository=AsyncMock(),
        news_repository=AsyncMock(),
        embedding_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
        finding_repository=AsyncMock(),
    )
    defaults.update(overrides)
    return MarketUniverseService(**defaults)


def _constituent(symbol: str = "TCS", company_id: uuid.UUID | None = None) -> UniverseConstituent:
    return UniverseConstituent(
        id=uuid.uuid4(),
        index_name="NIFTY50",
        symbol=symbol,
        company_id=company_id or uuid.uuid4(),
        ingestion_status=STATUS_READY,
    )


class TestComputeScore:
    @pytest.mark.asyncio
    async def test_fully_populated_company_scores_near_one(self):
        ohlcv = AsyncMock()
        ohlcv.get_summary_for_company.return_value = {
            "count": 250,
            "start_date": None,
            "end_date": datetime.now(UTC).date(),
        }
        indicators = AsyncMock()
        indicators.get_latest_snapshot.return_value = [object()]
        news = AsyncMock()
        news.list_by_company.return_value = [object()] * 10
        filings = AsyncMock()
        filings.list_by_company.return_value = [object()] * 5
        embeddings = AsyncMock()
        embeddings.get_checksums_by_company.return_value = {i: "x" for i in range(20)}

        service = _make_service(
            ohlcv_repository=ohlcv,
            indicator_repository=indicators,
            news_repository=news,
            filing_repository=filings,
            embedding_repository=embeddings,
        )

        result = await service.compute_score(uuid.uuid4())

        assert result.total == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_empty_company_scores_zero(self):
        ohlcv = AsyncMock()
        ohlcv.get_summary_for_company.return_value = {
            "count": 0,
            "start_date": None,
            "end_date": None,
        }
        indicators = AsyncMock()
        indicators.get_latest_snapshot.return_value = []
        news = AsyncMock()
        news.list_by_company.return_value = []
        filings = AsyncMock()
        filings.list_by_company.return_value = []
        embeddings = AsyncMock()
        embeddings.get_checksums_by_company.return_value = {}

        service = _make_service(
            ohlcv_repository=ohlcv,
            indicator_repository=indicators,
            news_repository=news,
            filing_repository=filings,
            embedding_repository=embeddings,
        )

        result = await service.compute_score(uuid.uuid4())

        assert result.total == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_stale_market_data_is_penalized(self):
        ohlcv = AsyncMock()
        ohlcv.get_summary_for_company.return_value = {
            "count": 250,
            "start_date": None,
            "end_date": (datetime.now(UTC) - timedelta(days=60)).date(),
        }
        service = _make_service(ohlcv_repository=ohlcv)
        service._indicators.get_latest_snapshot.return_value = []
        service._news.list_by_company.return_value = []
        service._filings.list_by_company.return_value = []
        service._embeddings.get_checksums_by_company.return_value = {}

        result = await service.compute_score(uuid.uuid4())

        # Full bar count but stale -> halved market_data component only.
        assert result.market_data == pytest.approx(0.5)


class TestScreen:
    @pytest.mark.asyncio
    async def test_marks_top_n_as_screened_in_and_rest_as_not(self):
        strong = _constituent("STRONG")
        weak = _constituent("WEAK")
        universe_repository = AsyncMock()
        universe_repository.list_by_index.return_value = [strong, weak]
        finding_repository = AsyncMock()
        finding_repository.get_latest.return_value = None  # always needs a committee run

        service = _make_service(
            universe_repository=universe_repository, finding_repository=finding_repository
        )
        service.compute_score = AsyncMock(
            side_effect=[
                ScreeningComponents(1.0, 1.0, 1.0, 1.0, 1.0),  # strong
                ScreeningComponents(0.0, 0.0, 0.0, 0.0, 0.0),  # weak
            ]
        )

        screened_in, committee_needed = await service.screen("NIFTY50", top_n=1)

        assert screened_in == ["STRONG"]
        assert committee_needed == ["STRONG"]
        assert universe_repository.update_screening.call_count == 2
        # Highest-scored constituent is marked in, the other is not.
        calls = {
            c.args[0].symbol: c.kwargs for c in universe_repository.update_screening.mock_calls
        }
        assert calls["STRONG"]["is_screened_in"] is True
        assert calls["WEAK"]["is_screened_in"] is False

    @pytest.mark.asyncio
    async def test_fresh_existing_committee_report_is_not_requeued(self):
        constituent = _constituent("TCS")
        universe_repository = AsyncMock()
        universe_repository.list_by_index.return_value = [constituent]

        fresh_finding = AsyncMock()
        fresh_finding.updated_at = datetime.now(UTC)
        finding_repository = AsyncMock()
        finding_repository.get_latest.return_value = fresh_finding

        service = _make_service(
            universe_repository=universe_repository, finding_repository=finding_repository
        )
        service.compute_score = AsyncMock(return_value=ScreeningComponents(1, 1, 1, 1, 1))

        screened_in, committee_needed = await service.screen("NIFTY50", top_n=25)

        assert screened_in == ["TCS"]
        assert committee_needed == []

    @pytest.mark.asyncio
    async def test_stale_existing_committee_report_is_requeued(self):
        constituent = _constituent("TCS")
        universe_repository = AsyncMock()
        universe_repository.list_by_index.return_value = [constituent]

        stale_finding = AsyncMock()
        stale_finding.updated_at = datetime.now(UTC) - timedelta(days=COMMITTEE_FRESHNESS_DAYS + 1)
        finding_repository = AsyncMock()
        finding_repository.get_latest.return_value = stale_finding

        service = _make_service(
            universe_repository=universe_repository, finding_repository=finding_repository
        )
        service.compute_score = AsyncMock(return_value=ScreeningComponents(1, 1, 1, 1, 1))

        _, committee_needed = await service.screen("NIFTY50", top_n=25)

        assert committee_needed == ["TCS"]

    @pytest.mark.asyncio
    async def test_candidates_without_financials_are_excluded_not_just_scored_low(self):
        """A candidate portfolio_planner's own Tier 1 filter would never
        select (no financial statements) must never reach a real
        Investment Committee run -- that LLM spend can never be
        recovered by any later portfolio (found via this version's own
        live verification: a financials-less real company was screened
        in on other evidence alone before this gate existed)."""
        no_financials = _constituent("NOFIN")
        has_financials = _constituent("HASFIN")
        universe_repository = AsyncMock()
        universe_repository.list_by_index.return_value = [no_financials, has_financials]

        statement_repository = AsyncMock()
        statement_repository.exists_for_company.side_effect = lambda company_id: (
            company_id == has_financials.company_id
        )
        finding_repository = AsyncMock()
        finding_repository.get_latest.return_value = None  # always needs a committee run

        service = _make_service(
            universe_repository=universe_repository,
            statement_repository=statement_repository,
            finding_repository=finding_repository,
        )
        service.compute_score = AsyncMock(return_value=ScreeningComponents(1, 1, 1, 1, 1))

        screened_in, committee_needed = await service.screen("NIFTY50", top_n=25)

        assert screened_in == ["HASFIN"]
        assert committee_needed == ["HASFIN"]
        service.compute_score.assert_called_once_with(has_financials.company_id)
        # The financials-less candidate is still recorded (score 0, not
        # screened in), not silently skipped.
        no_fin_call = next(
            c
            for c in universe_repository.update_screening.mock_calls
            if c.args[0].symbol == "NOFIN"
        )
        assert no_fin_call.kwargs == {"score": 0.0, "is_screened_in": False}


class TestSyncOne:
    @pytest.mark.asyncio
    async def test_missing_constituent_is_a_no_op(self):
        universe_repository = AsyncMock()
        universe_repository.get_by_symbol.return_value = None
        service = _make_service(universe_repository=universe_repository)

        await service.sync_one("NIFTY50", "NOPE")

        universe_repository.mark_ingesting.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingestion_failure_marks_constituent_failed_not_raised(self):
        constituent = _constituent("TCS")
        universe_repository = AsyncMock()
        universe_repository.get_by_symbol.return_value = constituent
        service = _make_service(universe_repository=universe_repository)
        service.ingest_constituent = AsyncMock(side_effect=RuntimeError("provider down"))

        await service.sync_one("NIFTY50", "TCS")  # must not raise

        universe_repository.mark_ingesting.assert_called_once_with(constituent)
        universe_repository.mark_failed.assert_called_once()
        universe_repository.mark_ready.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingestion_success_marks_constituent_ready(self):
        constituent = _constituent("TCS")
        company = AsyncMock()
        company.id = uuid.uuid4()
        universe_repository = AsyncMock()
        universe_repository.get_by_symbol.return_value = constituent
        service = _make_service(universe_repository=universe_repository)
        service.ingest_constituent = AsyncMock(return_value=company)

        await service.sync_one("NIFTY50", "TCS")

        universe_repository.mark_ready.assert_called_once_with(constituent, company_id=company.id)

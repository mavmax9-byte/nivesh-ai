from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.market_data.models import CorporateAction, HistoricalOHLCV
from nivesh.research.models import CompanyResearchDossier, ResearchVersion
from nivesh.research.service import ResearchPipelineService


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(),
        symbol=symbol,
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )
    company.exchange = exchange
    return company


def _dossier(company_id, version_number=0, watermark=None) -> CompanyResearchDossier:
    dossier = CompanyResearchDossier(id=uuid4(), company_id=company_id)
    dossier.current_version_number = version_number
    dossier.last_market_data_watermark = watermark
    return dossier


def _bar(trade_date: date, close: str) -> HistoricalOHLCV:
    return HistoricalOHLCV(
        id=uuid4(),
        trade_date=trade_date,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
        source="yfinance",
    )


def _make_service(
    company,
    dossier,
    ohlcv_summary,
    latest_bars,
    corporate_actions,
    version_return=None,
):
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    dossier_repository = AsyncMock()
    dossier_repository.get_or_create_dossier.return_value = dossier
    dossier_repository.get_by_company_id.return_value = dossier
    if version_return is not None:
        dossier_repository.create_version.return_value = version_return

    ohlcv_repository = AsyncMock()
    ohlcv_repository.get_summary_for_company.return_value = ohlcv_summary
    ohlcv_repository.list_for_company.return_value = latest_bars

    corporate_action_repository = AsyncMock()
    corporate_action_repository.list_for_company.return_value = corporate_actions

    service = ResearchPipelineService(
        company_repository=company_repository,
        dossier_repository=dossier_repository,
        ohlcv_repository=ohlcv_repository,
        corporate_action_repository=corporate_action_repository,
    )
    return service, dossier_repository


@pytest.mark.asyncio
async def test_refresh_dossier_creates_first_version_when_none_exists():
    company = _company()
    dossier = _dossier(company.id, version_number=0, watermark=None)
    version = ResearchVersion(id=uuid4(), dossier_id=dossier.id, version_number=1)

    service, dossier_repository = _make_service(
        company=company,
        dossier=dossier,
        ohlcv_summary={"count": 10, "start_date": date(2026, 1, 2), "end_date": date(2026, 1, 15)},
        latest_bars=[_bar(date(2026, 1, 15), "3500.00")],
        corporate_actions=[],
        version_return=version,
    )

    result = await service.refresh_dossier("TCS")

    assert result.changed is True
    assert result.version_number == 1
    assert result.symbol == "TCS"

    dossier_repository.create_version.assert_awaited_once()
    _, create_version_kwargs = dossier_repository.create_version.await_args
    assert create_version_kwargs["version_number"] == 1
    assert "Initial research version" in create_version_kwargs["change_summary"]

    dossier_repository.create_snapshot.assert_awaited_once()
    _, snapshot_kwargs = dossier_repository.create_snapshot.await_args
    assert snapshot_kwargs["price_bar_count"] == 10
    assert snapshot_kwargs["latest_price"] == Decimal("3500.00")

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert len(source_rows) == 1
    assert source_rows[0]["source_type"] == "market_data"
    assert source_rows[0]["record_count"] == 10

    dossier_repository.create_timeline_event.assert_awaited_once()
    dossier_repository.finalize_version.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_dossier_is_a_no_op_when_nothing_changed():
    company = _company()
    watermark = {"price_bar_count": 10, "latest_trade_date": "2026-01-15", "corporate_action_count": 0}
    dossier = _dossier(company.id, version_number=1, watermark=watermark)

    service, dossier_repository = _make_service(
        company=company,
        dossier=dossier,
        ohlcv_summary={"count": 10, "start_date": date(2026, 1, 2), "end_date": date(2026, 1, 15)},
        latest_bars=[_bar(date(2026, 1, 15), "3500.00")],
        corporate_actions=[],
    )

    result = await service.refresh_dossier("TCS")

    assert result.changed is False
    assert result.version_number == 1
    dossier_repository.create_version.assert_not_awaited()
    dossier_repository.finalize_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_dossier_creates_new_version_when_bars_increase():
    company = _company()
    watermark = {"price_bar_count": 10, "latest_trade_date": "2026-01-15", "corporate_action_count": 0}
    dossier = _dossier(company.id, version_number=1, watermark=watermark)
    version = ResearchVersion(id=uuid4(), dossier_id=dossier.id, version_number=2)

    service, dossier_repository = _make_service(
        company=company,
        dossier=dossier,
        ohlcv_summary={"count": 15, "start_date": date(2026, 1, 2), "end_date": date(2026, 1, 22)},
        latest_bars=[_bar(date(2026, 1, 22), "3550.00")],
        corporate_actions=[],
        version_return=version,
    )

    result = await service.refresh_dossier("TCS")

    assert result.changed is True
    assert result.version_number == 2
    _, kwargs = dossier_repository.create_version.await_args
    assert kwargs["change_summary"] == "5 new price bar(s) through 2026-01-22."


@pytest.mark.asyncio
async def test_refresh_dossier_creates_one_source_row_per_corporate_action():
    company = _company()
    dossier = _dossier(company.id, version_number=0, watermark=None)
    version = ResearchVersion(id=uuid4(), dossier_id=dossier.id, version_number=1)

    action_one = CorporateAction(
        id=uuid4(),
        company_id=company.id,
        action_type="split",
        ex_date=date(2026, 1, 10),
        ratio_numerator=2,
        ratio_denominator=1,
        source="yfinance",
    )
    action_two = CorporateAction(
        id=uuid4(),
        company_id=company.id,
        action_type="dividend",
        ex_date=date(2026, 1, 20),
        dividend_amount_per_share=Decimal("5.00"),
        source="yfinance",
    )

    service, dossier_repository = _make_service(
        company=company,
        dossier=dossier,
        ohlcv_summary={"count": 0, "start_date": None, "end_date": None},
        latest_bars=[],
        corporate_actions=[action_one, action_two],
        version_return=version,
    )

    await service.refresh_dossier("TCS")

    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert len(source_rows) == 2
    assert {row["reference_id"] for row in source_rows} == {action_one.id, action_two.id}
    assert all(row["source_type"] == "corporate_action" for row in source_rows)


@pytest.mark.asyncio
async def test_refresh_dossier_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None

    service = ResearchPipelineService(
        company_repository=company_repository,
        dossier_repository=AsyncMock(),
        ohlcv_repository=AsyncMock(),
        corporate_action_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.refresh_dossier("NOPE")


@pytest.mark.asyncio
async def test_get_dossier_overview_raises_not_found_when_no_dossier_yet():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = _company()

    dossier_repository = AsyncMock()
    dossier_repository.get_by_company_id.return_value = None

    service = ResearchPipelineService(
        company_repository=company_repository,
        dossier_repository=dossier_repository,
        ohlcv_repository=AsyncMock(),
        corporate_action_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.get_dossier_overview("TCS")


@pytest.mark.asyncio
async def test_get_latest_version_raises_not_found_when_no_versions_yet():
    company = _company()
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    dossier_repository = AsyncMock()
    dossier_repository.get_by_company_id.return_value = _dossier(company.id)
    dossier_repository.get_latest_version.return_value = None

    service = ResearchPipelineService(
        company_repository=company_repository,
        dossier_repository=dossier_repository,
        ohlcv_repository=AsyncMock(),
        corporate_action_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.get_latest_version("TCS")

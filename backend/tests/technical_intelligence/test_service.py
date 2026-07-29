from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.research.models import CompanyResearchDossier, ResearchVersion
from nivesh.technical_intelligence.models import TechnicalIndicator
from nivesh.technical_intelligence.providers.base import ProviderPriceBar
from nivesh.technical_intelligence.service import TechnicalIntelligenceService
from nivesh.technical_intelligence.validation import InsufficientHistoryError

_BASE_DATE = date(2026, 1, 1)


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


def _bars(count: int, price: float = 100.0) -> list[ProviderPriceBar]:
    bars = []
    for i in range(count):
        p = price + i * 0.5
        bars.append(
            ProviderPriceBar(
                trade_date=_BASE_DATE + timedelta(days=i),
                open=Decimal(str(p)),
                high=Decimal(str(p + 1)),
                low=Decimal(str(p - 1)),
                close=Decimal(str(p)),
                volume=1000 + i,
            )
        )
    return bars


def _make_service(company, *, latest_research_version=None, last_obv=None):
    provider = AsyncMock()

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    indicator_repository = AsyncMock()
    indicator_repository.get_last_indicator_value.return_value = last_obv
    indicator_repository.bulk_upsert.return_value = 0

    dossier_repository = AsyncMock()
    dossier_repository.get_or_create_dossier.return_value = CompanyResearchDossier(
        id=uuid4(), company_id=company.id
    )
    dossier_repository.get_latest_version.return_value = latest_research_version

    service = TechnicalIntelligenceService(
        provider=provider,
        company_repository=company_repository,
        indicator_repository=indicator_repository,
        dossier_repository=dossier_repository,
    )
    return service, provider, indicator_repository, dossier_repository


@pytest.mark.asyncio
async def test_generate_indicators_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = TechnicalIntelligenceService(
        provider=AsyncMock(),
        company_repository=company_repository,
        indicator_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.generate_indicators("NOPE")


@pytest.mark.asyncio
async def test_generate_indicators_raises_insufficient_history_for_too_few_bars():
    company = _company()
    service, provider, indicator_repository, _ = _make_service(company)
    provider.get_price_history.return_value = _bars(10)

    with pytest.raises(InsufficientHistoryError):
        await service.generate_indicators("TCS")

    indicator_repository.bulk_upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_indicators_persists_and_links_dossier():
    company = _company()
    version = ResearchVersion(id=uuid4(), dossier_id=uuid4(), version_number=1)
    service, provider, indicator_repository, dossier_repository = _make_service(
        company, latest_research_version=version
    )
    provider.get_price_history.return_value = _bars(30)

    result = await service.generate_indicators("TCS")

    assert result.indicators_generated > 0
    assert result.symbol == "TCS"

    indicator_repository.bulk_upsert.assert_awaited_once()
    (rows,) = indicator_repository.bulk_upsert.await_args.args
    assert all(row["company_id"] == company.id for row in rows)
    # sma_20 should be present with a 30-bar window; sma_200 should not.
    names = {row["indicator_name"] for row in rows}
    assert "sma_20" in names
    assert "sma_200" not in names

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert len(source_rows) == 1  # aggregate evidence, not one row per indicator
    assert source_rows[0]["source_type"] == "technical_indicator"
    assert source_rows[0]["record_count"] == len(rows)

    dossier_repository.create_timeline_event.assert_awaited_once()
    indicator_repository.commit.assert_awaited()


@pytest.mark.asyncio
async def test_generate_indicators_passes_obv_carry_forward_to_repository_lookup():
    company = _company()
    last_obv = TechnicalIndicator(
        id=uuid4(),
        company_id=company.id,
        trading_date=_BASE_DATE + timedelta(days=5),
        indicator_name="obv",
        indicator_parameters={},
        indicator_value=Decimal("5000"),
    )
    service, provider, indicator_repository, _ = _make_service(company, last_obv=last_obv)
    provider.get_price_history.return_value = _bars(30)

    await service.generate_indicators("TCS")

    indicator_repository.get_last_indicator_value.assert_awaited_once_with(company.id, "obv")
    (rows,) = indicator_repository.bulk_upsert.await_args.args
    obv_rows = [row for row in rows if row["indicator_name"] == "obv"]
    # Only OBV values for dates after the carried-forward date should be emitted.
    assert all(row["trading_date"] > last_obv.trading_date for row in obv_rows)


@pytest.mark.asyncio
async def test_generate_indicators_does_not_attach_evidence_without_research_version():
    company = _company()
    service, provider, indicator_repository, dossier_repository = _make_service(
        company, latest_research_version=None
    )
    provider.get_price_history.return_value = _bars(30)

    result = await service.generate_indicators("TCS")

    assert result.indicators_generated > 0
    dossier_repository.get_or_create_dossier.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_latest_indicators_delegates_to_repository():
    company = _company()
    service, _, indicator_repository, _ = _make_service(company)
    indicator_repository.get_latest_snapshot.return_value = []

    await service.get_latest_indicators("TCS")

    indicator_repository.get_latest_snapshot.assert_awaited_once_with(company.id)


@pytest.mark.asyncio
async def test_get_latest_indicators_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = TechnicalIntelligenceService(
        provider=AsyncMock(),
        company_repository=company_repository,
        indicator_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.get_latest_indicators("NOPE")


@pytest.mark.asyncio
async def test_get_indicator_history_delegates_to_repository():
    company = _company()
    service, _, indicator_repository, _ = _make_service(company)
    indicator_repository.get_history.return_value = []

    await service.get_indicator_history("TCS")

    indicator_repository.get_history.assert_awaited_once_with(company.id, limit=200, offset=0)


@pytest.mark.asyncio
async def test_get_indicators_by_name_delegates_to_repository():
    company = _company()
    service, _, indicator_repository, _ = _make_service(company)
    indicator_repository.get_history_by_indicator.return_value = []

    await service.get_indicators_by_name("TCS", "rsi_14")

    indicator_repository.get_history_by_indicator.assert_awaited_once_with(
        company.id, "rsi_14", limit=200, offset=0
    )

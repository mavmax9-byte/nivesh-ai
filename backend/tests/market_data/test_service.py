from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.market_data.providers.base import (
    ProviderCompanyMetadata,
    ProviderCorporateAction,
    ProviderOHLCVBar,
)
from nivesh.market_data.service import MarketDataService


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


@pytest.mark.asyncio
async def test_sync_company_orchestrates_the_full_pipeline():
    company = _company()

    provider = AsyncMock()
    provider.get_company_metadata.return_value = ProviderCompanyMetadata(
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange_code="NSE",
        sector="Technology",
        industry="IT Services",
        currency="INR",
    )
    provider.get_historical_ohlcv.return_value = [
        ProviderOHLCVBar(
            date(2026, 1, 2), Decimal("100"), Decimal("105"), Decimal("99"), Decimal("104"), 1000
        ),
        # Invalid: negative open price -- must be skipped, not synced.
        ProviderOHLCVBar(
            date(2026, 1, 3), Decimal("-1"), Decimal("105"), Decimal("99"), Decimal("104"), 1000
        ),
    ]
    provider.get_corporate_actions.return_value = [
        ProviderCorporateAction("dividend", date(2026, 2, 1), None, None, Decimal("5.0")),
    ]

    exchange_repository = AsyncMock()
    exchange_repository.get_or_create_by_code.return_value = company.exchange

    company_repository = AsyncMock()
    company_repository.upsert.return_value = company

    ohlcv_repository = AsyncMock()
    ohlcv_repository.bulk_upsert.return_value = 1

    corporate_action_repository = AsyncMock()
    corporate_action_repository.bulk_upsert.return_value = 1

    service = MarketDataService(
        provider=provider,
        company_repository=company_repository,
        exchange_repository=exchange_repository,
        ohlcv_repository=ohlcv_repository,
        corporate_action_repository=corporate_action_repository,
    )

    result = await service.sync_company("TCS")

    assert result.symbol == "TCS"
    assert result.company_id == company.id
    assert result.bars_synced == 1
    assert result.bars_skipped == 1
    assert result.actions_synced == 1

    company_repository.upsert.assert_awaited_once()
    _, upsert_kwargs = company_repository.upsert.await_args
    assert upsert_kwargs["symbol"] == "TCS"
    assert upsert_kwargs["exchange_id"] == company.exchange.id

    ohlcv_repository.bulk_upsert.assert_awaited_once()
    (normalized_rows,) = ohlcv_repository.bulk_upsert.await_args.args
    assert len(normalized_rows) == 1
    assert normalized_rows[0]["company_id"] == company.id


@pytest.mark.asyncio
async def test_sync_company_uses_default_five_year_window_when_not_specified():
    company = _company()

    provider = AsyncMock()
    provider.get_company_metadata.return_value = ProviderCompanyMetadata(
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange_code="NSE",
        sector=None,
        industry=None,
        currency=None,
    )
    provider.get_historical_ohlcv.return_value = []
    provider.get_corporate_actions.return_value = []

    exchange_repository = AsyncMock()
    exchange_repository.get_or_create_by_code.return_value = company.exchange
    company_repository = AsyncMock()
    company_repository.upsert.return_value = company
    ohlcv_repository = AsyncMock()
    ohlcv_repository.bulk_upsert.return_value = 0
    corporate_action_repository = AsyncMock()
    corporate_action_repository.bulk_upsert.return_value = 0

    service = MarketDataService(
        provider, company_repository, exchange_repository, ohlcv_repository, corporate_action_repository
    )

    await service.sync_company("TCS")

    _, call_kwargs = provider.get_historical_ohlcv.await_args
    assert (call_kwargs["end"] - call_kwargs["start"]).days >= 365 * 4


@pytest.mark.asyncio
async def test_get_history_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None

    service = MarketDataService(
        AsyncMock(), company_repository, AsyncMock(), AsyncMock(), AsyncMock()
    )

    with pytest.raises(NotFoundError):
        await service.get_history("NOPE")


@pytest.mark.asyncio
async def test_get_history_returns_bars_for_known_symbol():
    company = _company()
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    ohlcv_repository = AsyncMock()
    ohlcv_repository.list_for_company.return_value = ["bar-1", "bar-2"]

    service = MarketDataService(
        AsyncMock(), company_repository, AsyncMock(), ohlcv_repository, AsyncMock()
    )

    bars = await service.get_history("TCS")

    assert bars == ["bar-1", "bar-2"]
    ohlcv_repository.list_for_company.assert_awaited_once_with(
        company.id, start=None, end=None, limit=1000
    )

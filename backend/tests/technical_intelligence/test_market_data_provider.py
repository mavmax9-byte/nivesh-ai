from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.market_data.models import HistoricalOHLCV
from nivesh.technical_intelligence.providers.exceptions import TechnicalDataProviderError
from nivesh.technical_intelligence.providers.market_data_provider import PersistedOHLCVProvider


def _ohlcv(trade_date: date) -> HistoricalOHLCV:
    return HistoricalOHLCV(
        id=uuid4(),
        company_id=uuid4(),
        trade_date=trade_date,
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("99.00"),
        close=Decimal("102.00"),
        volume=1000,
        source="yfinance-dev",
    )


@pytest.mark.asyncio
async def test_get_price_history_reverses_repository_order_to_chronological():
    company_id = uuid4()
    ohlcv_repository = AsyncMock()
    # Repository returns newest-first, as HistoricalOHLCVRepository.list_for_company does.
    ohlcv_repository.list_for_company.return_value = [
        _ohlcv(date(2026, 1, 3)),
        _ohlcv(date(2026, 1, 2)),
        _ohlcv(date(2026, 1, 1)),
    ]
    provider = PersistedOHLCVProvider(ohlcv_repository)

    bars = await provider.get_price_history(company_id, limit=300)

    assert [bar.trade_date for bar in bars] == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]
    ohlcv_repository.list_for_company.assert_awaited_once_with(company_id, limit=300)


@pytest.mark.asyncio
async def test_get_price_history_returns_empty_list_for_no_history():
    ohlcv_repository = AsyncMock()
    ohlcv_repository.list_for_company.return_value = []
    provider = PersistedOHLCVProvider(ohlcv_repository)

    bars = await provider.get_price_history(uuid4(), limit=300)

    assert bars == []


@pytest.mark.asyncio
async def test_get_price_history_wraps_repository_errors():
    ohlcv_repository = AsyncMock()
    ohlcv_repository.list_for_company.side_effect = RuntimeError("connection lost")
    provider = PersistedOHLCVProvider(ohlcv_repository)

    with pytest.raises(TechnicalDataProviderError):
        await provider.get_price_history(uuid4(), limit=300)

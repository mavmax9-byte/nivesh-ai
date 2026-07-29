"""Technical data provider interface.

Unlike every other provider in this codebase, the concrete implementation
here does not call an external API -- it reads OHLCV bars market_data's own
sync has already persisted to `historical_ohlcv`, satisfying "reuse the
existing Market Data provider... rather than creating duplicate
market-data fetching logic" without a second yfinance call (see
market_data_provider.py). The abstraction is still worth keeping (rather
than importing `HistoricalOHLCVRepository` directly into the service) for
the same reason every other provider boundary exists:
`TechnicalIntelligenceService` depends only on `TechnicalDataProvider`,
never a concrete repository or client, so where price history comes from
could change later (a different persistence layer, a bounded cache, a
dedicated bars service) without touching the service.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ProviderPriceBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class TechnicalDataProvider(ABC):
    """Abstract contract every technical data provider must implement."""

    @abstractmethod
    async def get_price_history(self, company_id: uuid.UUID, limit: int) -> list[ProviderPriceBar]:
        """Fetch up to `limit` most recent daily OHLCV bars for a company,
        ordered oldest to newest."""
        raise NotImplementedError

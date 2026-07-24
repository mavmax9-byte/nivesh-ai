"""Market data provider interface.

The application depends only on `MarketDataProvider` -- never on a concrete
provider. Every provider (the development provider today, a commercial
provider later) returns these normalized DTOs, never raw provider payloads,
so swapping a provider never touches business logic (docs/v1
02-System-Architecture.md section 2.4's adapter-pattern rationale, applied
here at the code level).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ProviderCompanySearchResult:
    symbol: str
    name: str
    exchange_code: str


@dataclass(frozen=True)
class ProviderCompanyMetadata:
    symbol: str
    name: str
    exchange_code: str
    sector: str | None
    industry: str | None
    currency: str | None


@dataclass(frozen=True)
class ProviderOHLCVBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class ProviderLatestPrice:
    symbol: str
    price: Decimal
    as_of: date


@dataclass(frozen=True)
class ProviderCorporateAction:
    action_type: str  # "split" | "dividend"
    ex_date: date
    ratio_numerator: int | None
    ratio_denominator: int | None
    dividend_amount_per_share: Decimal | None


class MarketDataProvider(ABC):
    """Abstract contract every market data provider must implement."""

    @abstractmethod
    async def search_companies(self, query: str) -> list[ProviderCompanySearchResult]:
        """Search for companies by name or symbol fragment."""
        raise NotImplementedError

    @abstractmethod
    async def get_company_metadata(self, symbol: str) -> ProviderCompanyMetadata:
        """Fetch current company metadata for an exact symbol."""
        raise NotImplementedError

    @abstractmethod
    async def get_historical_ohlcv(
        self, symbol: str, start: date, end: date
    ) -> list[ProviderOHLCVBar]:
        """Fetch daily OHLCV bars for a symbol over a date range."""
        raise NotImplementedError

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> ProviderLatestPrice:
        """Fetch the most recent available price for a symbol."""
        raise NotImplementedError

    @abstractmethod
    async def get_corporate_actions(self, symbol: str) -> list[ProviderCorporateAction]:
        """Fetch known corporate actions (splits, dividends) for a symbol."""
        raise NotImplementedError

"""Market data domain service.

Orchestrates provider fetches, validation, normalization, and persistence.
Business rules are limited to sequencing and defaults -- validation lives in
validation.py, normalization in normalization.py, and persistence in the
repository classes, kept separate on purpose.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.market_data.models import HistoricalOHLCV
from nivesh.market_data.normalization import normalize_corporate_action, normalize_ohlcv_bar
from nivesh.market_data.providers.base import MarketDataProvider
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.market_data.validation import is_valid_ohlcv_bar, validate_company_metadata

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_YEARS = 5
PROVIDER_SOURCE_NAME = "yfinance"


@dataclass(frozen=True)
class MarketSyncResult:
    company_id: uuid.UUID
    symbol: str
    bars_synced: int
    bars_skipped: int
    actions_synced: int


class MarketDataService:
    def __init__(
        self,
        provider: MarketDataProvider,
        company_repository: CompanyRepository,
        exchange_repository: ExchangeRepository,
        ohlcv_repository: HistoricalOHLCVRepository,
        corporate_action_repository: CorporateActionRepository,
    ) -> None:
        self._provider = provider
        self._companies = company_repository
        self._exchanges = exchange_repository
        self._ohlcv = ohlcv_repository
        self._corporate_actions = corporate_action_repository

    async def sync_company(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> MarketSyncResult:
        end = end or date.today()
        start = start or end - timedelta(days=365 * DEFAULT_HISTORY_YEARS)

        metadata = await self._provider.get_company_metadata(symbol)
        validate_company_metadata(metadata)

        exchange = await self._exchanges.get_or_create_by_code(metadata.exchange_code)
        company = await self._companies.upsert(
            symbol=metadata.symbol,
            name=metadata.name,
            exchange_id=exchange.id,
            sector=metadata.sector,
            industry=metadata.industry,
        )

        raw_bars = await self._provider.get_historical_ohlcv(symbol, start=start, end=end)
        valid_bars = [bar for bar in raw_bars if is_valid_ohlcv_bar(bar)]
        skipped = len(raw_bars) - len(valid_bars)
        if skipped:
            logger.warning(
                "market_data_bars_skipped",
                extra={"symbol": symbol, "skipped": skipped, "total": len(raw_bars)},
            )
        normalized_bars = [
            normalize_ohlcv_bar(company.id, bar, source=PROVIDER_SOURCE_NAME) for bar in valid_bars
        ]
        bars_synced = await self._ohlcv.bulk_upsert(normalized_bars)

        raw_actions = await self._provider.get_corporate_actions(symbol)
        normalized_actions = [
            normalize_corporate_action(company.id, action, source=PROVIDER_SOURCE_NAME)
            for action in raw_actions
        ]
        actions_synced = await self._corporate_actions.bulk_upsert(normalized_actions)

        return MarketSyncResult(
            company_id=company.id,
            symbol=company.symbol,
            bars_synced=bars_synced,
            bars_skipped=skipped,
            actions_synced=actions_synced,
        )

    async def get_history(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 1000,
    ) -> list[HistoricalOHLCV]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._ohlcv.list_for_company(company.id, start=start, end=end, limit=limit)

"""Technical data provider backed by market_data's already-persisted OHLCV history.

Reuses `HistoricalOHLCVRepository.list_for_company` (market_data/repository.py)
rather than fetching fresh bars from yfinance -- indicator generation is
triggered *after* market_data's own sync has already written the bars this
module needs (see ingestion/tasks.py), so a second external fetch would be
duplicate work re-fetching data that already exists. Isolated behind
`TechnicalDataProvider` like every other provider in this codebase: if
price history ever needs to come from somewhere else, only this file and
factory.py change.
"""

import uuid

from nivesh.market_data.repository import HistoricalOHLCVRepository
from nivesh.technical_intelligence.providers.base import ProviderPriceBar, TechnicalDataProvider
from nivesh.technical_intelligence.providers.exceptions import TechnicalDataProviderError


class PersistedOHLCVProvider(TechnicalDataProvider):
    def __init__(self, ohlcv_repository: HistoricalOHLCVRepository) -> None:
        self._ohlcv = ohlcv_repository

    async def get_price_history(self, company_id: uuid.UUID, limit: int) -> list[ProviderPriceBar]:
        try:
            bars = await self._ohlcv.list_for_company(company_id, limit=limit)
        except Exception as exc:
            raise TechnicalDataProviderError(
                f"Failed to read OHLCV history for company '{company_id}': {exc}"
            ) from exc

        # list_for_company returns newest-first; indicator computation needs
        # chronological (oldest-first) order.
        return [
            ProviderPriceBar(
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in reversed(bars)
        ]

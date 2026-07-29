"""Provider factory -- the one place a concrete provider is chosen.

Unlike every other provider factory in this codebase (which take no
arguments, since they call external HTTP/yfinance clients needing no
database session), this one takes the caller's already-open
`HistoricalOHLCVRepository` -- the concrete provider reads already-
persisted OHLCV bars from Postgres on the same request-scoped session as
the rest of the service, rather than opening a second session of its own.
"""

from nivesh.market_data.repository import HistoricalOHLCVRepository
from nivesh.technical_intelligence.providers.base import TechnicalDataProvider
from nivesh.technical_intelligence.providers.market_data_provider import PersistedOHLCVProvider


def get_technical_data_provider(
    ohlcv_repository: HistoricalOHLCVRepository,
) -> TechnicalDataProvider:
    return PersistedOHLCVProvider(ohlcv_repository)

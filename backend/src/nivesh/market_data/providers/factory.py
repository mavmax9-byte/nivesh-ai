"""Provider factory -- the one place a concrete provider is chosen."""

from nivesh.market_data.providers.base import MarketDataProvider
from nivesh.market_data.providers.yfinance_provider import YFinanceProvider


def get_market_data_provider() -> MarketDataProvider:
    return YFinanceProvider()

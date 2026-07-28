"""Provider factory -- the one place a concrete provider is chosen."""

from nivesh.news_intelligence.providers.base import NewsProvider
from nivesh.news_intelligence.providers.yfinance_provider import YFinanceNewsProvider


def get_news_provider() -> NewsProvider:
    return YFinanceNewsProvider()

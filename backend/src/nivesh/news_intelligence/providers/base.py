"""News provider interface.

Mirrors market_data/providers/base.py, financials/providers/base.py, and
corporate_filings/providers/base.py's adapter pattern: the application
depends only on `NewsProvider`, never a concrete provider. Every provider
returns these normalized DTOs, never raw provider payloads, so additional
providers (Reuters, Economic Times, Moneycontrol, Google News, etc.) can be
added later by writing one new class and changing one line in
factory.py -- NewsIntelligenceService never needs to change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProviderNewsArticle:
    title: str
    source: str
    author: str | None
    published_at: datetime
    url: str
    summary: str
    full_content: str | None
    language: str


class NewsProvider(ABC):
    """Abstract contract every news provider must implement."""

    @abstractmethod
    async def get_news(self, symbol: str) -> list[ProviderNewsArticle]:
        """Fetch recent news articles for a symbol, most recent first."""
        raise NotImplementedError

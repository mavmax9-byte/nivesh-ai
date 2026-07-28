"""Development news provider, backed by Yahoo Finance via yfinance.

Chosen for the same reasons as the sibling market_data, financials, and
corporate_filings yfinance providers: no API key, reachable for NSE/BSE-
listed equities, well-suited to local development. Fully isolated behind
`NewsProvider` -- a real news API (Reuters, Economic Times, Moneycontrol,
Google News, etc.) can replace or sit alongside it later without touching
`NewsIntelligenceService`.

`Ticker.news` returns a list of items shaped as
`{"id": ..., "content": {"title", "summary", "pubDate", "provider":
{"displayName"}, "canonicalUrl": {"url", "lang"}, ...}}` -- the current
yfinance/Yahoo Finance news schema, confirmed against live data for this
sprint. `content.provider.displayName` is exactly the "originating
publication" (e.g. "Reuters", "Bloomberg") this module stores as `source`.
yfinance does not expose an article author or the full article body for
this endpoint -- `author` and `full_content` are always `None` from this
provider, consistent with the requirement that both are "if/when
available." Items missing a title or url are skipped rather than raising,
since one malformed item in an otherwise-good response should not fail the
whole sync.
"""

import asyncio
from datetime import UTC, datetime

import yfinance as yf

from nivesh.news_intelligence.providers.base import NewsProvider, ProviderNewsArticle
from nivesh.news_intelligence.providers.exceptions import NewsProviderError

_EXCHANGE_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_DEFAULT_EXCHANGE = "NSE"
_DEFAULT_LANGUAGE = "en"


def _to_yahoo_symbol(symbol: str, exchange_code: str = _DEFAULT_EXCHANGE) -> str:
    upper_symbol = symbol.upper()
    if any(upper_symbol.endswith(suffix) for suffix in _EXCHANGE_SUFFIX.values()):
        return upper_symbol
    suffix = _EXCHANGE_SUFFIX.get(exchange_code.upper(), _EXCHANGE_SUFFIX[_DEFAULT_EXCHANGE])
    return f"{upper_symbol}{suffix}"


def _parse_published_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_language(canonical_url: dict) -> str:
    lang = canonical_url.get("lang") or ""
    return lang.split("-")[0].lower() if lang else _DEFAULT_LANGUAGE


def _parse_item(item: dict) -> ProviderNewsArticle | None:
    content = item.get("content") or {}
    title = content.get("title")
    canonical_url = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
    url = canonical_url.get("url")
    if not title or not url:
        return None

    published_at = _parse_published_at(content.get("pubDate")) or datetime.now(UTC)
    provider_info = content.get("provider") or {}
    source = provider_info.get("displayName") or "Unknown"

    return ProviderNewsArticle(
        title=title,
        source=source,
        author=None,
        published_at=published_at,
        url=url,
        summary=content.get("summary") or "",
        full_content=None,
        language=_parse_language(canonical_url),
    )


class YFinanceNewsProvider(NewsProvider):
    async def get_news(self, symbol: str) -> list[ProviderNewsArticle]:
        return await asyncio.to_thread(self._fetch, symbol)

    def _fetch(self, symbol: str) -> list[ProviderNewsArticle]:
        yahoo_symbol = _to_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)

        try:
            raw_items = ticker.news or []
        except Exception as exc:
            raise NewsProviderError(f"News fetch failed for '{symbol}': {exc}") from exc

        articles = [_parse_item(item) for item in raw_items]
        return [article for article in articles if article is not None]

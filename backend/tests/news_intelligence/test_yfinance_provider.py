from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest

from nivesh.news_intelligence.providers.exceptions import NewsProviderError
from nivesh.news_intelligence.providers.yfinance_provider import (
    YFinanceNewsProvider,
    _parse_item,
    _parse_language,
    _parse_published_at,
    _to_yahoo_symbol,
)


def _raw_item(**content_overrides) -> dict:
    content = dict(
        title="India's TCS rises after quarterly revenue beat",
        summary="TCS shares rose after reporting quarterly revenue ahead of estimates.",
        pubDate="2026-07-10T03:56:27Z",
        provider={"displayName": "Reuters", "url": "https://www.reuters.com/"},
        canonicalUrl={
            "url": "https://sg.finance.yahoo.com/news/indias-tcs-rises-quarterly-revenue.html",
            "lang": "en-SG",
        },
    )
    content.update(content_overrides)
    return {"id": "abc123", "content": content}


def test_to_yahoo_symbol_defaults_to_nse():
    assert _to_yahoo_symbol("TCS") == "TCS.NS"


def test_parse_published_at_handles_z_suffix():
    parsed = _parse_published_at("2026-07-10T03:56:27Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.year == 2026 and parsed.month == 7 and parsed.day == 10


def test_parse_published_at_returns_none_for_missing_value():
    assert _parse_published_at(None) is None


def test_parse_published_at_returns_none_for_malformed_value():
    assert _parse_published_at("not-a-date") is None


def test_parse_language_extracts_primary_subtag():
    assert _parse_language({"lang": "en-SG"}) == "en"


def test_parse_language_defaults_to_en_when_missing():
    assert _parse_language({}) == "en"


def test_parse_item_maps_all_available_fields():
    article = _parse_item(_raw_item())

    assert article is not None
    assert article.title == "India's TCS rises after quarterly revenue beat"
    assert article.source == "Reuters"
    assert article.author is None
    assert article.full_content is None
    assert article.language == "en"
    assert (
        article.url == "https://sg.finance.yahoo.com/news/indias-tcs-rises-quarterly-revenue.html"
    )
    assert article.published_at.tzinfo is not None


def test_parse_item_falls_back_to_click_through_url():
    item = _raw_item(canonicalUrl=None, clickThroughUrl={"url": "https://example.com/story"})
    article = _parse_item(item)
    assert article is not None
    assert article.url == "https://example.com/story"


def test_parse_item_returns_none_when_title_missing():
    item = _raw_item(title=None)
    assert _parse_item(item) is None


def test_parse_item_returns_none_when_url_missing():
    item = _raw_item(canonicalUrl={}, clickThroughUrl=None)
    assert _parse_item(item) is None


def test_parse_item_defaults_missing_provider_to_unknown():
    item = _raw_item(provider=None)
    article = _parse_item(item)
    assert article is not None
    assert article.source == "Unknown"


def test_parse_item_uses_now_when_pub_date_missing():
    item = _raw_item(pubDate=None)
    article = _parse_item(item)
    assert article is not None
    assert article.published_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_get_news_parses_and_skips_malformed_items():
    provider = YFinanceNewsProvider()
    mock_ticker = MagicMock()
    mock_ticker.news = [_raw_item(), _raw_item(title=None)]

    with patch(
        "nivesh.news_intelligence.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        articles = await provider.get_news("TCS")

    assert len(articles) == 1
    assert articles[0].source == "Reuters"


@pytest.mark.asyncio
async def test_get_news_handles_none_news_list():
    provider = YFinanceNewsProvider()
    mock_ticker = MagicMock()
    mock_ticker.news = None

    with patch(
        "nivesh.news_intelligence.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker
    ):
        articles = await provider.get_news("TCS")

    assert articles == []


@pytest.mark.asyncio
async def test_get_news_raises_provider_error_when_fetch_fails():
    provider = YFinanceNewsProvider()
    mock_ticker = MagicMock()
    type(mock_ticker).news = property(lambda self: (_ for _ in ()).throw(RuntimeError("down")))

    with (
        patch(
            "nivesh.news_intelligence.providers.yfinance_provider.yf.Ticker",
            return_value=mock_ticker,
        ),
        pytest.raises(NewsProviderError),
    ):
        await provider.get_news("TCS")

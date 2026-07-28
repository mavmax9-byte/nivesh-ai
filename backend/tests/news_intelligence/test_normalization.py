import uuid
from datetime import UTC, datetime

from nivesh.news_intelligence.models import (
    CATEGORY_CORPORATE_ACTION,
    CATEGORY_EARNINGS,
    CATEGORY_GENERAL,
    CATEGORY_MARKETS,
    CATEGORY_REGULATORY,
)
from nivesh.news_intelligence.normalization import (
    canonicalize_url,
    categorize,
    compute_checksum,
    normalize_article,
)
from nivesh.news_intelligence.providers.base import ProviderNewsArticle


def _provider_article(**overrides) -> ProviderNewsArticle:
    defaults: dict = dict(
        title="Brokerage raises TCS target price after strong show",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 10, 3, 56, 27, tzinfo=UTC),
        url="https://sg.finance.yahoo.com/news/indias-tcs-rises-quarterly-revenue-035627890.html",
        summary="TCS shares rose after the company reported quarterly revenue ahead of estimates.",
        full_content=None,
        language="en",
    )
    defaults.update(overrides)
    return ProviderNewsArticle(**defaults)


def test_categorize_detects_earnings_keywords():
    assert categorize("TCS Q1 2027 Earnings Call Highlights") == CATEGORY_EARNINGS


def test_categorize_detects_corporate_action_keywords():
    assert categorize("TCS board approves share buyback") == CATEGORY_CORPORATE_ACTION


def test_categorize_detects_regulatory_keywords():
    assert categorize("SEBI issues notice to TCS over disclosure lapse") == CATEGORY_REGULATORY


def test_categorize_detects_markets_keywords():
    assert categorize("TCS target price raised by brokerage") == CATEGORY_MARKETS


def test_categorize_defaults_to_general():
    assert categorize("TCS opens industrial AI lab in Bengaluru") == CATEGORY_GENERAL


def test_categorize_is_case_insensitive():
    assert categorize("TCS ANNOUNCES DIVIDEND FOR SHAREHOLDERS") == CATEGORY_CORPORATE_ACTION


def test_canonicalize_url_strips_query_and_fragment():
    assert (
        canonicalize_url("https://Example.com/News/story?utm_source=x#section")
        == "https://example.com/News/story"
    )


def test_canonicalize_url_strips_trailing_slash():
    assert canonicalize_url("https://example.com/news/story/") == canonicalize_url(
        "https://example.com/news/story"
    )


def test_compute_checksum_is_deterministic():
    company_id = uuid.uuid4()
    url = "https://example.com/story"
    first = compute_checksum(company_id, "yfinance-dev", url)
    second = compute_checksum(company_id, "yfinance-dev", url)
    assert first == second
    assert len(first) == 64


def test_compute_checksum_differs_per_provider():
    """Dedup is scoped per-provider only (v0.5 decision) -- the same URL
    from two different providers must NOT collide."""
    company_id = uuid.uuid4()
    url = "https://example.com/story"
    yfinance_checksum = compute_checksum(company_id, "yfinance-dev", url)
    other_provider_checksum = compute_checksum(company_id, "reuters-dev", url)
    assert yfinance_checksum != other_provider_checksum


def test_compute_checksum_differs_per_company():
    url = "https://example.com/story"
    first = compute_checksum(uuid.uuid4(), "yfinance-dev", url)
    second = compute_checksum(uuid.uuid4(), "yfinance-dev", url)
    assert first != second


def test_normalize_article_maps_all_fields():
    company_id = uuid.uuid4()
    article = _provider_article()

    data = normalize_article(company_id=company_id, provider_code="yfinance-dev", article=article)

    assert data["company_id"] == company_id
    assert data["title"] == article.title
    assert data["source"] == article.source
    assert data["author"] is None
    assert data["published_at"] == article.published_at
    assert data["url"] == article.url
    assert data["summary"] == article.summary
    assert data["full_content"] is None
    assert data["language"] == "en"
    assert data["category"] == CATEGORY_MARKETS
    assert data["provider"] == "yfinance-dev"
    assert data["checksum"] == compute_checksum(company_id, "yfinance-dev", article.url)

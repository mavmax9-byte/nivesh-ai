"""Normalization of provider DTOs into repository-ready persistence payloads.

Pure functions -- no I/O, no side effects.

Deduplication scope: `compute_checksum` intentionally folds `provider` into
the dedup key (`sha256(company_id | provider | canonical_url)`), so
deduplication is scoped **per-provider only** in this version -- re-syncing
the same provider's results is idempotent, but two different providers
reporting the same real-world story via different URLs are stored as two
separate NewsArticle rows rather than merged into one. This was an explicit
choice (over a fuzzier title/date-based cross-provider match) made during
v0.5 planning: with only one real provider in production so far, designing
true cross-provider identity resolution now would be speculative and hard
to validate; it is deferred to a future version once a second provider
exists to design and test that matching logic against real data. See
models.py's module docstring.

Category assignment is a small, fixed keyword -> category lookup applied to
the article title -- the same "string-shape heuristic, not AI"
classification approach document_intelligence/normalization.py uses for
heading detection, not a machine-learned or LLM-based classifier. Every
article that matches no keyword is "general".
"""

import hashlib
import uuid
from urllib.parse import urlparse, urlunparse

from nivesh.news_intelligence.models import (
    CATEGORY_CORPORATE_ACTION,
    CATEGORY_EARNINGS,
    CATEGORY_GENERAL,
    CATEGORY_MARKETS,
    CATEGORY_REGULATORY,
)
from nivesh.news_intelligence.providers.base import ProviderNewsArticle

# Deterministic keyword -> category mapping, checked in this order (first
# match wins) against the lowercased article title.
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        CATEGORY_EARNINGS,
        ("earnings", "quarterly result", "q1 20", "q2 20", "q3 20", "q4 20", "profit", "revenue"),
    ),
    (
        CATEGORY_CORPORATE_ACTION,
        (
            "dividend",
            "bonus issue",
            "buyback",
            "stock split",
            "rights issue",
            "merger",
            "acquisition",
            "amalgamation",
        ),
    ),
    (
        CATEGORY_REGULATORY,
        ("sebi", "regulatory", "compliance", "penalty", "notice", "investigation"),
    ),
    (
        CATEGORY_MARKETS,
        (
            "share price",
            "stock price",
            "market cap",
            "target price",
            "rating",
            "shares rise",
            "shares fall",
            "shares set",
        ),
    ),
)


def categorize(title: str) -> str:
    lowered = title.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return CATEGORY_GENERAL


def canonicalize_url(url: str) -> str:
    """Strips query params and fragments and lowercases scheme/host, so
    trivially different links to the same page (tracking params, case,
    trailing slash) dedupe identically."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def compute_checksum(company_id: uuid.UUID, provider_code: str, url: str) -> str:
    canonical_url = canonicalize_url(url)
    digest = hashlib.sha256(f"{company_id}|{provider_code}|{canonical_url}".encode()).hexdigest()
    return digest


def normalize_article(
    *, company_id: uuid.UUID, provider_code: str, article: ProviderNewsArticle
) -> dict:
    return {
        "company_id": company_id,
        "title": article.title,
        "source": article.source,
        "author": article.author,
        "published_at": article.published_at,
        "url": article.url,
        "summary": article.summary,
        "full_content": article.full_content,
        "language": article.language,
        "category": categorize(article.title),
        "provider": provider_code,
        "checksum": compute_checksum(company_id, provider_code, article.url),
    }

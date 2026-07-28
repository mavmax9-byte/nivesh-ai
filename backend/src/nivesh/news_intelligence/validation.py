"""Pure validation rules for provider-sourced news articles.

No I/O, no side effects -- kept separate from NewsIntelligenceService so the
rules are independently testable and reusable regardless of which provider
or which service method needs them, mirroring corporate_filings/
financials/document_intelligence's validation.py separation.

Checksum *uniqueness* needs a database lookup and so is enforced by the
service (via NewsArticleRepository.get_by_checksum) and by the
`uq_news_articles_checksum` constraint, not here -- this module only
validates the checksum's own format.
"""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from fastapi import status

from nivesh.core.exceptions import NiveshError
from nivesh.news_intelligence.models import VALID_NEWS_CATEGORIES

REQUIRED_NEWS_FIELDS = ("title", "source", "url", "language", "category", "provider")

# Hex digest, e.g. a SHA-256 checksum (64 hex chars) -- the length a
# checksum must be at least as long as to be a meaningful content
# fingerprint rather than a placeholder string.
_CHECKSUM_PATTERN = re.compile(r"^[0-9a-fA-F]{32,}$")
_MAX_FUTURE_SKEW = timedelta(days=1)


class InvalidNewsDataError(NiveshError):
    """Raised when provider-sourced news data fails a validation rule that
    should halt persistence of that article."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_NEWS_DATA"


def validate_required_fields(data: dict) -> None:
    for field in REQUIRED_NEWS_FIELDS:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise InvalidNewsDataError(f"News article is missing required field '{field}'.")


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidNewsDataError(f"'{url}' is not a valid http(s) URL.")


def validate_published_at(published_at: datetime) -> None:
    if published_at.tzinfo is None:
        raise InvalidNewsDataError("published_at must be timezone-aware.")
    if published_at > datetime.now(UTC) + _MAX_FUTURE_SKEW:
        raise InvalidNewsDataError(
            f"published_at '{published_at}' is implausibly far in the future."
        )


def validate_category(category: str) -> None:
    if category not in VALID_NEWS_CATEGORIES:
        raise InvalidNewsDataError(f"Unknown category '{category}'.")


def validate_checksum_format(checksum: str) -> None:
    if not _CHECKSUM_PATTERN.match(checksum):
        raise InvalidNewsDataError(
            f"'{checksum}' is not a valid checksum "
            "(expected a hex digest of at least 32 characters)."
        )

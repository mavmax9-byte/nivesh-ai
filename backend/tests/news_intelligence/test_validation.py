from datetime import UTC, datetime, timedelta

import pytest

from nivesh.news_intelligence.validation import (
    InvalidNewsDataError,
    validate_category,
    validate_checksum_format,
    validate_published_at,
    validate_required_fields,
    validate_url,
)

_VALID_CHECKSUM = "a" * 64


def _article_data(**overrides) -> dict:
    defaults = dict(
        title="TCS rises after quarterly revenue beat",
        source="Reuters",
        url="https://finance.yahoo.com/news/tcs-rises-quarterly-revenue.html",
        language="en",
        category="markets",
        provider="yfinance-dev",
    )
    defaults.update(overrides)
    return defaults


def test_valid_https_url_passes():
    validate_url("https://finance.yahoo.com/news/some-story.html")  # should not raise


def test_url_without_scheme_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_url("finance.yahoo.com/news/some-story.html")


def test_url_with_unsupported_scheme_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_url("ftp://finance.yahoo.com/news/some-story.html")


def test_url_without_host_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_url("https://")


def test_published_at_with_timezone_passes():
    validate_published_at(datetime.now(UTC))  # should not raise


def test_published_at_without_timezone_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_published_at(datetime.now())  # noqa: DTZ005


def test_published_at_far_in_the_future_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_published_at(datetime.now(UTC) + timedelta(days=30))


def test_published_at_slightly_in_the_future_is_allowed():
    validate_published_at(datetime.now(UTC) + timedelta(hours=1))  # should not raise


def test_valid_category_passes():
    validate_category("earnings")  # should not raise


def test_unknown_category_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_category("gossip")


def test_valid_checksum_passes():
    validate_checksum_format(_VALID_CHECKSUM)  # should not raise


def test_short_checksum_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_checksum_format("abc123")


def test_non_hex_checksum_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_checksum_format("z" * 64)


def test_required_fields_all_present_passes():
    validate_required_fields(_article_data())  # should not raise


def test_required_fields_missing_title_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_required_fields(_article_data(title=""))


def test_required_fields_missing_source_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_required_fields(_article_data(source=None))


def test_required_fields_missing_url_is_rejected():
    with pytest.raises(InvalidNewsDataError):
        validate_required_fields(_article_data(url=""))

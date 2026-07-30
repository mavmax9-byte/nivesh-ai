import pytest

from nivesh.retrieval_engine.validation import (
    InvalidRetrievalQueryError,
    validate_limit,
    validate_query,
)


def test_validate_query_accepts_real_text():
    validate_query("What is TCS's latest revenue?")


def test_validate_query_rejects_empty_string():
    with pytest.raises(InvalidRetrievalQueryError):
        validate_query("")


def test_validate_query_rejects_whitespace_only():
    with pytest.raises(InvalidRetrievalQueryError):
        validate_query("   ")


def test_validate_limit_accepts_positive_values():
    validate_limit(1)
    validate_limit(100)


def test_validate_limit_rejects_zero_or_negative():
    with pytest.raises(InvalidRetrievalQueryError):
        validate_limit(0)
    with pytest.raises(InvalidRetrievalQueryError):
        validate_limit(-1)

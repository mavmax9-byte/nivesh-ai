import pytest

from nivesh.knowledge_layer.validation import (
    InvalidKnowledgeTextError,
    validate_non_empty_text,
)


def test_validate_non_empty_text_accepts_real_text():
    validate_non_empty_text("Tata Consultancy Services is an IT services company.")


def test_validate_non_empty_text_rejects_empty_string():
    with pytest.raises(InvalidKnowledgeTextError):
        validate_non_empty_text("")


def test_validate_non_empty_text_rejects_whitespace_only():
    with pytest.raises(InvalidKnowledgeTextError):
        validate_non_empty_text("   \n\t  ")

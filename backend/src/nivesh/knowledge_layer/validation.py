"""Pure validation rules for text before it is sent to the embedding
provider.

No I/O, no side effects -- kept separate from KnowledgeLayerService,
mirroring every other module's validation.py separation.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class InvalidKnowledgeTextError(NiveshError):
    """Raised when a knowledge unit's text fails a validation rule that
    should skip embedding it."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_KNOWLEDGE_TEXT"


def validate_non_empty_text(text: str) -> None:
    if not text or not text.strip():
        raise InvalidKnowledgeTextError("Cannot embed empty or whitespace-only text.")

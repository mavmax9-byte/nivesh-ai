"""Pure validation rules for retrieval requests.

No I/O, no side effects -- mirrors every other module's validation.py
separation.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class InvalidRetrievalQueryError(NiveshError):
    """Raised when a retrieval request's query text fails a validation
    rule that should halt the request."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_RETRIEVAL_QUERY"


def validate_query(query: str) -> None:
    if not query or not query.strip():
        raise InvalidRetrievalQueryError("Retrieval query must not be empty.")


def validate_limit(limit: int) -> None:
    if limit < 1:
        raise InvalidRetrievalQueryError("limit must be at least 1.")

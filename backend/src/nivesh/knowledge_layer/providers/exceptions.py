"""Embedding provider-layer exceptions.

Subclasses NiveshError so it flows through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring. Only one
exception class, the same single-class shape technical_intelligence's
provider layer uses (no "not found" concept applies to generating an
embedding, unlike a lookup-style provider) -- a missing/invalid API key is
also surfaced as this same error rather than a dedicated subtype, since
it's still, from the caller's point of view, "the embedding provider could
not produce a result."
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class EmbeddingProviderError(NiveshError):
    """Raised when the embedding provider fails (missing/invalid API key,
    network, upstream, malformed response)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "EMBEDDING_PROVIDER_ERROR"

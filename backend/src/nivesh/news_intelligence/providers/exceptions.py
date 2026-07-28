"""News provider-layer exceptions.

Subclass NiveshError so they flow through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class NewsProviderError(NiveshError):
    """Raised when a news provider fails (network, upstream, parsing)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "NEWS_PROVIDER_ERROR"


class NewsNotFoundError(NewsProviderError):
    """Raised when a provider has no news for the requested symbol."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NEWS_NOT_FOUND"

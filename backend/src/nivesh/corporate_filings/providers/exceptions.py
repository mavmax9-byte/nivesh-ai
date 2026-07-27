"""Corporate filings provider-layer exceptions.

Subclass NiveshError so they flow through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class FilingsProviderError(NiveshError):
    """Raised when a corporate filings provider fails (network, upstream, parsing)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "FILINGS_PROVIDER_ERROR"


class FilingsNotFoundError(FilingsProviderError):
    """Raised when a provider has no filings for the requested symbol."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "FILINGS_NOT_FOUND"

"""Provider-layer exceptions.

Subclass NiveshError so they flow through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class ProviderError(NiveshError):
    """Raised when a market data provider fails (network, upstream, parsing)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "PROVIDER_ERROR"


class SymbolNotFoundError(ProviderError):
    """Raised when a provider has no data for the requested symbol."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "SYMBOL_NOT_FOUND"

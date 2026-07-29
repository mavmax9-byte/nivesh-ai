"""Technical data provider-layer exceptions.

Subclasses NiveshError so it flows through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class TechnicalDataProviderError(NiveshError):
    """Raised when reading persisted OHLCV history for indicator
    computation fails unexpectedly (e.g. a database error)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "TECHNICAL_DATA_PROVIDER_ERROR"

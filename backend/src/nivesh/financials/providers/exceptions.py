"""Financial data provider-layer exceptions.

Subclass NiveshError so they flow through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class FinancialProviderError(NiveshError):
    """Raised when a financial data provider fails (network, upstream, parsing)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "FINANCIAL_PROVIDER_ERROR"


class FinancialDataNotFoundError(FinancialProviderError):
    """Raised when a provider has no financial statements for the requested symbol."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "FINANCIAL_DATA_NOT_FOUND"

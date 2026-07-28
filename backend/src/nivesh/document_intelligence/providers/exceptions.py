"""Document extraction provider-layer exceptions.

Subclass NiveshError so they flow through the existing exception-handler
middleware (nivesh.core.exceptions) without any additional wiring, mirroring
market_data/corporate_filings/financials' provider exceptions.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class DocumentExtractionProviderError(NiveshError):
    """Raised when a document extraction provider fails (network, download,
    or parsing failure)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "DOCUMENT_EXTRACTION_PROVIDER_ERROR"


class DocumentNotFoundError(DocumentExtractionProviderError):
    """Raised when the document at a filing version's source_url cannot be
    retrieved (e.g. a 404 from the upstream host)."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "DOCUMENT_NOT_FOUND"

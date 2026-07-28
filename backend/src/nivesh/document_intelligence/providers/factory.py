"""Provider factory -- the one place a concrete provider is chosen."""

from nivesh.document_intelligence.providers.base import DocumentExtractionProvider
from nivesh.document_intelligence.providers.http_provider import HttpDocumentExtractionProvider


def get_document_extraction_provider() -> DocumentExtractionProvider:
    return HttpDocumentExtractionProvider()

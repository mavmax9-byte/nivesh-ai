"""Document extraction provider interface.

Mirrors market_data/providers/base.py, financials/providers/base.py, and
corporate_filings/providers/base.py's adapter pattern: the application
depends only on `DocumentExtractionProvider`, never a concrete provider.
Every provider returns these normalized DTOs, never a raw document blob, so
a different extraction backend (a different PDF library, an OCR-backed
provider for scanned filings, a commercial extraction API) can replace the
development provider later without touching `DocumentIntelligenceService`.

A provider's job stops at "mechanically pull text out of the document, page
by page" -- it does not attempt heading/section detection itself. That
interpretation step is deterministic but heavier, and lives in
normalization.py so it is independently testable regardless of which
provider produced the raw pages.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ProviderExtractionResult:
    extractor_name: str
    extractor_version: str
    pages: list[ProviderExtractedPage]


class DocumentExtractionProvider(ABC):
    """Abstract contract every document extraction provider must implement."""

    @abstractmethod
    async def extract(self, source_url: str) -> ProviderExtractionResult:
        """Fetches the document at `source_url` and returns its text, per page.

        `source_url` is the same pointer-only URL Corporate Filings already
        stores (FilingVersion.source_url) -- this module never stores the
        document itself, only what this call returns.
        """
        raise NotImplementedError

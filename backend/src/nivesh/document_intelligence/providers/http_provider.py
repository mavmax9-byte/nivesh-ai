"""Development document extraction provider, backed by pypdf and
BeautifulSoup4.

Named after what it actually is -- a plain HTTP fetch of whatever document
`source_url` points to, with format-appropriate parsing chosen from what
comes back -- rather than after one format, because both formats are real
here: `source_url` is Corporate Filings' own pointer field, and today's
development filings provider (corporate_filings' yfinance-backed provider)
populates it with exchange investor-relations pages (HTML), while a real
NSE/BSE announcements feed plugged in later would populate it with direct
PDF links, which is what annual reports, quarterly results, and investor
presentations almost always actually are. Handling both honestly reflects
both realities without this module needing to know or care which upstream
filings provider produced the URL.

pypdf is a pure-Python PDF parser (no system dependencies such as poppler
or tesseract) and BeautifulSoup4 (via the already-installed lxml parser)
is the standard deterministic HTML-to-text tool; both are adequate for
local development and testing. Fully isolated behind
`DocumentExtractionProvider` -- an OCR-capable or commercial extraction
provider can replace this later without touching
`DocumentIntelligenceService`.

The document is downloaded once, in full, into memory and handed to the
appropriate parser; nothing about the downloaded bytes is persisted
anywhere -- only the text a parser extracts from them ever reaches the
database (see models.py's "Do NOT store PDFs" constraint).
"""

import asyncio
from io import BytesIO

import bs4
import httpx
import pypdf

from nivesh.document_intelligence.providers.base import (
    DocumentExtractionProvider,
    ProviderExtractedPage,
    ProviderExtractionResult,
)
from nivesh.document_intelligence.providers.exceptions import (
    DocumentExtractionProviderError,
    DocumentNotFoundError,
)

_PDF_EXTRACTOR_NAME = "pypdf"
_HTML_EXTRACTOR_NAME = "beautifulsoup4"
_DOWNLOAD_TIMEOUT_SECONDS = 30.0
_PDF_MAGIC_BYTES = b"%PDF-"


class HttpDocumentExtractionProvider(DocumentExtractionProvider):
    async def extract(self, source_url: str) -> ProviderExtractionResult:
        content, content_type = await self._download(source_url)
        if self._is_pdf(content, content_type):
            return await asyncio.to_thread(self._parse_pdf, content)
        return await asyncio.to_thread(self._parse_html, content)

    async def _download(self, source_url: str) -> tuple[bytes, str]:
        try:
            async with httpx.AsyncClient(
                timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True
            ) as client:
                response = await client.get(source_url)
        except httpx.HTTPError as exc:
            raise DocumentExtractionProviderError(
                f"Document download failed for '{source_url}': {exc}"
            ) from exc

        if response.status_code == 404:
            raise DocumentNotFoundError(f"No document found at '{source_url}'")
        if response.is_error:
            raise DocumentExtractionProviderError(
                f"Document download failed for '{source_url}': HTTP {response.status_code}"
            )
        return response.content, response.headers.get("content-type", "")

    def _is_pdf(self, content: bytes, content_type: str) -> bool:
        if "pdf" in content_type.lower():
            return True
        return content.lstrip().startswith(_PDF_MAGIC_BYTES)

    def _parse_pdf(self, content: bytes) -> ProviderExtractionResult:
        try:
            reader = pypdf.PdfReader(BytesIO(content))
            pages = [
                ProviderExtractedPage(page_number=index + 1, text=page.extract_text() or "")
                for index, page in enumerate(reader.pages)
            ]
        except Exception as exc:
            raise DocumentExtractionProviderError(f"PDF parsing failed: {exc}") from exc

        return ProviderExtractionResult(
            extractor_name=_PDF_EXTRACTOR_NAME,
            extractor_version=pypdf.__version__,
            pages=pages,
        )

    def _parse_html(self, content: bytes) -> ProviderExtractionResult:
        try:
            soup = bs4.BeautifulSoup(content, "lxml")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
        except Exception as exc:
            raise DocumentExtractionProviderError(f"HTML parsing failed: {exc}") from exc

        return ProviderExtractionResult(
            extractor_name=_HTML_EXTRACTOR_NAME,
            extractor_version=bs4.__version__,
            pages=[ProviderExtractedPage(page_number=1, text=text)],
        )

"""Tests for the pypdf/BeautifulSoup4-backed document extraction provider.

Mirrors market_data/corporate_filings' yfinance provider tests: the
external library (`httpx` for the download, `pypdf`/`bs4` for parsing) is
mocked at its own entry point rather than hitting the network or parsing a
real document.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nivesh.document_intelligence.providers.exceptions import (
    DocumentExtractionProviderError,
    DocumentNotFoundError,
)
from nivesh.document_intelligence.providers.http_provider import HttpDocumentExtractionProvider


def _mock_response(
    status_code: int = 200, content: bytes = b"%PDF-1.4 fake", content_type: str = "application/pdf"
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.is_error = status_code >= 400
    response.content = content
    response.headers = {"content-type": content_type}
    return response


def _mock_client_context(response: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.get.return_value = response
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=False)
    return context_manager


def _mock_pdf_reader(pages_text: list[str | None]) -> MagicMock:
    reader = MagicMock()
    pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    reader.pages = pages
    return reader


@pytest.mark.asyncio
async def test_extract_returns_pages_with_one_based_page_numbers():
    provider = HttpDocumentExtractionProvider()
    response = _mock_response()

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=_mock_client_context(response),
        ),
        patch(
            "nivesh.document_intelligence.providers.http_provider.pypdf.PdfReader",
            return_value=_mock_pdf_reader(["Page one text", "Page two text"]),
        ),
    ):
        result = await provider.extract("https://example.com/report.pdf")

    assert result.extractor_name == "pypdf"
    assert [page.page_number for page in result.pages] == [1, 2]
    assert result.pages[0].text == "Page one text"
    assert result.pages[1].text == "Page two text"


@pytest.mark.asyncio
async def test_extract_treats_none_extract_text_as_empty_string():
    provider = HttpDocumentExtractionProvider()
    response = _mock_response()

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=_mock_client_context(response),
        ),
        patch(
            "nivesh.document_intelligence.providers.http_provider.pypdf.PdfReader",
            return_value=_mock_pdf_reader([None]),
        ),
    ):
        result = await provider.extract("https://example.com/scanned.pdf")

    assert result.pages[0].text == ""


@pytest.mark.asyncio
async def test_extract_detects_pdf_by_magic_bytes_when_content_type_is_generic():
    provider = HttpDocumentExtractionProvider()
    response = _mock_response(content=b"%PDF-1.7 real", content_type="application/octet-stream")

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=_mock_client_context(response),
        ),
        patch(
            "nivesh.document_intelligence.providers.http_provider.pypdf.PdfReader",
            return_value=_mock_pdf_reader(["Text"]),
        ),
    ):
        result = await provider.extract("https://example.com/download")

    assert result.extractor_name == "pypdf"


@pytest.mark.asyncio
async def test_extract_parses_html_document_as_single_page():
    provider = HttpDocumentExtractionProvider()
    html = (
        b"<html><head><style>.a{}</style></head><body><h1>Title</h1><p>Body text.</p></body></html>"
    )
    response = _mock_response(content=html, content_type="text/html; charset=utf-8")

    with patch(
        "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
        return_value=_mock_client_context(response),
    ):
        result = await provider.extract("https://example.com/page.html")

    assert result.extractor_name == "beautifulsoup4"
    assert len(result.pages) == 1
    assert result.pages[0].page_number == 1
    assert "Title" in result.pages[0].text
    assert "Body text." in result.pages[0].text


@pytest.mark.asyncio
async def test_extract_html_strips_script_and_style_content():
    provider = HttpDocumentExtractionProvider()
    html = (
        b"<html><body><script>var secret = 'not-content';</script>"
        b"<style>.hidden{display:none}</style><p>Visible text.</p></body></html>"
    )
    response = _mock_response(content=html, content_type="text/html")

    with patch(
        "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
        return_value=_mock_client_context(response),
    ):
        result = await provider.extract("https://example.com/page.html")

    assert "not-content" not in result.pages[0].text
    assert "Visible text." in result.pages[0].text


@pytest.mark.asyncio
async def test_extract_raises_not_found_for_404():
    provider = HttpDocumentExtractionProvider()
    response = _mock_response(status_code=404)

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=_mock_client_context(response),
        ),
        pytest.raises(DocumentNotFoundError),
    ):
        await provider.extract("https://example.com/missing.pdf")


@pytest.mark.asyncio
async def test_extract_raises_provider_error_for_server_error():
    provider = HttpDocumentExtractionProvider()
    response = _mock_response(status_code=502)

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=_mock_client_context(response),
        ),
        pytest.raises(DocumentExtractionProviderError),
    ):
        await provider.extract("https://example.com/report.pdf")


@pytest.mark.asyncio
async def test_extract_raises_provider_error_when_download_raises_http_error():
    provider = HttpDocumentExtractionProvider()
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("no route"))
    context_manager.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=context_manager,
        ),
        pytest.raises(DocumentExtractionProviderError),
    ):
        await provider.extract("https://example.com/report.pdf")


@pytest.mark.asyncio
async def test_extract_raises_provider_error_when_pdf_parsing_fails():
    provider = HttpDocumentExtractionProvider()
    response = _mock_response()

    with (
        patch(
            "nivesh.document_intelligence.providers.http_provider.httpx.AsyncClient",
            return_value=_mock_client_context(response),
        ),
        patch(
            "nivesh.document_intelligence.providers.http_provider.pypdf.PdfReader",
            side_effect=RuntimeError("corrupted PDF"),
        ),
        pytest.raises(DocumentExtractionProviderError),
    ):
        await provider.extract("https://example.com/report.pdf")

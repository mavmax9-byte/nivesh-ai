from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.document_intelligence.models import (
    EXTRACTION_STATUS_COMPLETED,
    DocumentExtraction,
    DocumentSection,
)
from nivesh.document_intelligence.router import get_document_intelligence_service
from nivesh.main import create_app


def _extraction(**overrides) -> DocumentExtraction:
    defaults = dict(
        id=uuid4(),
        filing_version_id=uuid4(),
        company_id=uuid4(),
        extraction_status=EXTRACTION_STATUS_COMPLETED,
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="--- Page 1 ---\nANNUAL REPORT\nBody text.",
        page_count=1,
        section_count=1,
    )
    defaults.update(overrides)
    extraction = DocumentExtraction(**defaults)
    extraction.created_at = datetime(2026, 10, 15, 9, 0, 0)
    extraction.updated_at = datetime(2026, 10, 15, 9, 0, 0)
    extraction.sections = [
        DocumentSection(
            id=uuid4(),
            document_extraction_id=extraction.id,
            sequence=0,
            heading="ANNUAL REPORT",
            level=1,
            page_number=1,
            content="Body text.",
        )
    ]
    return extraction


@pytest.mark.asyncio
async def test_get_document_extraction_by_filing_version_returns_detail():
    app = create_app()
    filing_version_id = uuid4()
    mock_service = AsyncMock()
    mock_service.get_extraction.return_value = _extraction(filing_version_id=filing_version_id)
    app.dependency_overrides[get_document_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/document-intelligence/filing-versions/{filing_version_id}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["extraction_status"] == "completed"
    assert body["filing_version_id"] == str(filing_version_id)
    assert body["sections"][0]["heading"] == "ANNUAL REPORT"
    assert "--- Page 1 ---" in body["extracted_text"]
    mock_service.get_extraction.assert_awaited_once_with(filing_version_id)


@pytest.mark.asyncio
async def test_get_document_extraction_returns_404_when_not_yet_extracted():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_extraction.side_effect = NotFoundError(
        "No document extraction exists yet for filing version"
    )
    app.dependency_overrides[get_document_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/document-intelligence/filing-versions/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_document_extractions_for_symbol_returns_light_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_extractions_for_symbol.return_value = [_extraction()]
    app.dependency_overrides[get_document_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/document-intelligence/tcs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert "extracted_text" not in body[0]
    assert "sections" not in body[0]
    mock_service.get_extractions_for_symbol.assert_awaited_once_with("tcs", limit=50, offset=0)


@pytest.mark.asyncio
async def test_get_document_extractions_for_symbol_returns_404_for_unknown_company():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_extractions_for_symbol.side_effect = NotFoundError(
        "No company found with symbol 'NOPE'"
    )
    app.dependency_overrides[get_document_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/document-intelligence/NOPE")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_extract_document_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)
    filing_version_id = uuid4()

    with patch("nivesh.document_intelligence.router.extract_filing_document") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-123")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/document-intelligence/extract/{filing_version_id}"
            )

    assert response.status_code == 202
    body = response.json()
    assert body["filing_version_id"] == str(filing_version_id)
    assert body["status"] == "queued"
    assert body["task_id"] == "task-123"
    mock_task.delay.assert_called_once_with(str(filing_version_id))

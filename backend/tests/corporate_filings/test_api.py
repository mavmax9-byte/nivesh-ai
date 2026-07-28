from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import (
    CorporateFiling,
    FilingCategory,
    FilingSource,
    FilingVersion,
)
from nivesh.corporate_filings.router import get_corporate_filings_service
from nivesh.main import create_app


def _filing(**overrides) -> CorporateFiling:
    defaults = dict(
        id=uuid4(),
        company_id=uuid4(),
        exchange="NSE",
        filing_type="quarterly_results",
        category_id=uuid4(),
        source_id=uuid4(),
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum="a" * 64,
        language="en",
        document_size=None,
        version_number=1,
    )
    defaults.update(overrides)
    filing = CorporateFiling(**defaults)
    filing.ingestion_timestamp = datetime(2026, 10, 15, 9, 0, 0)
    filing.created_at = datetime(2026, 10, 15, 9, 0, 0)
    filing.updated_at = datetime(2026, 10, 15, 9, 0, 0)
    filing.category = FilingCategory(
        id=defaults["category_id"], code="financial_results", name="Financial Results"
    )
    filing.source = FilingSource(
        id=defaults["source_id"], code="yfinance-dev", name="Development Provider"
    )
    return filing


def _filing_version(**overrides) -> FilingVersion:
    defaults = dict(
        id=uuid4(),
        filing_id=uuid4(),
        company_id=uuid4(),
        version_number=1,
        title="TCS Quarterly Results - Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum="a" * 64,
        document_size=None,
    )
    defaults.update(overrides)
    version = FilingVersion(**defaults)
    version.recorded_at = datetime(2026, 10, 15, 9, 0, 0)
    return version


@pytest.mark.asyncio
async def test_get_filings_returns_filing_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_filings.return_value = [_filing()]
    app.dependency_overrides[get_corporate_filings_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/filings/tcs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filing_type"] == "quarterly_results"
    assert body[0]["category"]["code"] == "financial_results"
    assert body[0]["source"]["code"] == "yfinance-dev"
    mock_service.get_filings.assert_awaited_once_with("tcs", limit=50, offset=0)


@pytest.mark.asyncio
async def test_get_filings_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_filings.side_effect = NotFoundError("No company found with symbol 'NOPE'")
    app.dependency_overrides[get_corporate_filings_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/filings/NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_annual_filings_returns_filing_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_annual_filings.return_value = [_filing(filing_type="annual_report")]
    app.dependency_overrides[get_corporate_filings_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/filings/tcs/annual")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filing_type"] == "annual_report"


@pytest.mark.asyncio
async def test_get_quarterly_filings_returns_filing_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_quarterly_filings.return_value = [_filing()]
    app.dependency_overrides[get_corporate_filings_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/filings/tcs/quarterly?limit=10")

    assert response.status_code == 200
    mock_service.get_quarterly_filings.assert_awaited_once_with("tcs", limit=10)


@pytest.mark.asyncio
async def test_get_filings_by_category_returns_filtered_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_filings_by_category.return_value = [_filing(filing_type="board_meeting")]
    app.dependency_overrides[get_corporate_filings_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/filings/tcs/category/governance")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    mock_service.get_filings_by_category.assert_awaited_once_with("tcs", "governance", limit=50)


@pytest.mark.asyncio
async def test_get_filing_history_returns_version_list():
    app = create_app()
    version = _filing_version(version_number=2)
    mock_service = AsyncMock()
    mock_service.get_filing_history.return_value = [version]
    app.dependency_overrides[get_corporate_filings_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/filings/tcs/history")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["version_number"] == 2
    # id must be exposed so a client can discover a filing_version_id to
    # call the Document Intelligence endpoints with (v0.4).
    assert body[0]["id"] == str(version.id)


@pytest.mark.asyncio
async def test_sync_filings_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.corporate_filings.router.sync_company_filings") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-789")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/filings/sync/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-789"
    mock_task.delay.assert_called_once_with("TCS")

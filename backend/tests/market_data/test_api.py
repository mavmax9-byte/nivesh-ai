from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.companies.models import Company, Exchange
from nivesh.companies.router import get_company_service
from nivesh.core.exceptions import NotFoundError
from nivesh.main import create_app
from nivesh.market_data.models import HistoricalOHLCV
from nivesh.market_data.router import get_market_data_service


def _company() -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(), symbol="TCS", name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    company.sector = "Technology"
    company.industry = "IT Services"
    company.is_active = True
    return company


@pytest.mark.asyncio
async def test_list_companies_returns_companies():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.list_companies.return_value = [_company()]
    app.dependency_overrides[get_company_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/companies")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "TCS"
    assert body[0]["exchange"]["code"] == "NSE"


@pytest.mark.asyncio
async def test_get_company_by_symbol_returns_company():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_by_symbol.return_value = _company()
    app.dependency_overrides[get_company_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/companies/TCS")

    assert response.status_code == 200
    assert response.json()["symbol"] == "TCS"


@pytest.mark.asyncio
async def test_get_company_by_symbol_returns_404_when_not_found():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_by_symbol.side_effect = NotFoundError("No company found with symbol 'NOPE'")
    app.dependency_overrides[get_company_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/companies/NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_sync_market_data_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.market_data.router.sync_company_market_data") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-123")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/market/sync/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-123"
    mock_task.delay.assert_called_once_with("TCS")


@pytest.mark.asyncio
async def test_get_market_history_returns_bars():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_history.return_value = [
        HistoricalOHLCV(
            trade_date=date(2026, 1, 2),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("104"),
            volume=1000,
        )
    ]
    app.dependency_overrides[get_market_data_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/market/history/tcs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert float(body[0]["close"]) == 104.0
    assert body[0]["volume"] == 1000


@pytest.mark.asyncio
async def test_get_market_history_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_history.side_effect = NotFoundError("No company found with symbol 'NOPE'")
    app.dependency_overrides[get_market_data_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/market/history/NOPE")

    assert response.status_code == 404

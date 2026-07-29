from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.main import create_app
from nivesh.technical_intelligence.models import TechnicalIndicator
from nivesh.technical_intelligence.router import get_technical_intelligence_service


def _indicator(**overrides) -> TechnicalIndicator:
    defaults = dict(
        id=uuid4(),
        company_id=uuid4(),
        trading_date=date(2026, 7, 27),
        indicator_name="sma_20",
        indicator_parameters={"period": 20},
        indicator_value=Decimal("2295.60"),
    )
    defaults.update(overrides)
    indicator = TechnicalIndicator(**defaults)
    indicator.calculation_timestamp = datetime(2026, 7, 27, 18, 0, 0, tzinfo=UTC)
    indicator.created_at = datetime(2026, 7, 27, 18, 0, 0, tzinfo=UTC)
    indicator.updated_at = datetime(2026, 7, 27, 18, 0, 0, tzinfo=UTC)
    return indicator


@pytest.mark.asyncio
async def test_generate_indicators_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.technical_intelligence.router.generate_technical_indicators") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-654")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/technical/generate/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-654"
    mock_task.delay.assert_called_once_with("TCS")


@pytest.mark.asyncio
async def test_get_latest_indicators_returns_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_indicators.return_value = [_indicator()]
    app.dependency_overrides[get_technical_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/technical/tcs/latest")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["indicator_name"] == "sma_20"
    assert body[0]["indicator_parameters"] == {"period": 20}
    mock_service.get_latest_indicators.assert_awaited_once_with("tcs")


@pytest.mark.asyncio
async def test_get_latest_indicators_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_indicators.side_effect = NotFoundError(
        "No company found with symbol 'NOPE'"
    )
    app.dependency_overrides[get_technical_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/technical/NOPE/latest")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_indicator_history_returns_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_indicator_history.return_value = [_indicator()]
    app.dependency_overrides[get_technical_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/technical/tcs/history?limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    mock_service.get_indicator_history.assert_awaited_once_with("tcs", limit=10, offset=0)


@pytest.mark.asyncio
async def test_get_indicators_by_name_returns_filtered_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_indicators_by_name.return_value = [_indicator(indicator_name="rsi_14")]
    app.dependency_overrides[get_technical_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/technical/tcs/indicator/rsi_14")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["indicator_name"] == "rsi_14"
    mock_service.get_indicators_by_name.assert_awaited_once_with(
        "tcs", "rsi_14", limit=200, offset=0
    )

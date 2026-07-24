from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.main import create_app
from nivesh.research.models import ResearchSnapshot, ResearchTimeline, ResearchVersion
from nivesh.research.router import get_research_service
from nivesh.research.service import DossierOverview


def _snapshot(**overrides) -> ResearchSnapshot:
    defaults = dict(
        id=uuid4(),
        version_id=uuid4(),
        company_id=uuid4(),
        sector="Technology",
        industry="IT Services",
        latest_price=Decimal("3500.00"),
        latest_trade_date=date(2026, 1, 15),
        price_bar_count=10,
        price_history_start=date(2026, 1, 2),
        price_history_end=date(2026, 1, 15),
        corporate_action_count=0,
        latest_corporate_action_date=None,
    )
    defaults.update(overrides)
    return ResearchSnapshot(**defaults)


def _version(version_number: int = 1) -> ResearchVersion:
    version = ResearchVersion(
        id=uuid4(),
        dossier_id=uuid4(),
        version_number=version_number,
        triggered_by="market_data_sync",
        change_summary="Initial research version: 10 price bar(s) through 2026-01-15, 0 corporate action(s).",
    )
    version.created_at = datetime(2026, 1, 15, 18, 0, 0)
    version.snapshot = _snapshot()
    return version


@pytest.mark.asyncio
async def test_get_research_dossier_returns_full_overview():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_dossier_overview.return_value = DossierOverview(
        symbol="TCS",
        current_version_number=1,
        last_refreshed_at=datetime(2026, 1, 15, 18, 0, 0),
        latest_version=_version(),
        recent_timeline=[
            ResearchTimeline(
                id=uuid4(),
                dossier_id=uuid4(),
                company_id=uuid4(),
                event_type="version_created",
                description="Initial research version.",
                event_timestamp=datetime(2026, 1, 15, 18, 0, 0),
            )
        ],
        evidence_counts={"market_data": 10},
    )
    app.dependency_overrides[get_research_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/research/tcs")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["current_version_number"] == 1
    assert body["latest_version"]["version_number"] == 1
    assert body["latest_version"]["snapshot"]["price_bar_count"] == 10
    assert len(body["recent_timeline"]) == 1
    assert body["evidence_summary"] == [{"source_type": "market_data", "record_count": 10}]


@pytest.mark.asyncio
async def test_get_research_dossier_returns_404_when_no_dossier_yet():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_dossier_overview.side_effect = NotFoundError(
        "No research dossier exists yet for symbol 'TCS'"
    )
    app.dependency_overrides[get_research_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/research/tcs")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_research_history_returns_versions_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_version_history.return_value = [_version(2), _version(1)]
    app.dependency_overrides[get_research_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/research/tcs/history")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["version_number"] == 2
    assert body[1]["version_number"] == 1
    mock_service.get_version_history.assert_awaited_once_with("tcs", limit=50, offset=0)


@pytest.mark.asyncio
async def test_get_research_latest_returns_single_version():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_version.return_value = _version(3)
    app.dependency_overrides[get_research_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/research/tcs/latest")

    assert response.status_code == 200
    assert response.json()["version_number"] == 3


@pytest.mark.asyncio
async def test_get_research_latest_returns_404_when_no_versions_yet():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_version.side_effect = NotFoundError(
        "No research version exists yet for symbol 'TCS'"
    )
    app.dependency_overrides[get_research_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/research/tcs/latest")

    assert response.status_code == 404

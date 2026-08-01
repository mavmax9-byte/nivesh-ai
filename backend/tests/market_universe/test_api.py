import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.main import create_app
from nivesh.market_universe.models import UniverseConstituent


async def _fake_get_db():
    yield MagicMock()


def _constituent_row(**overrides) -> UniverseConstituent:
    defaults = dict(
        id=uuid.uuid4(),
        index_name="NIFTY50",
        symbol="TCS",
        company_id=uuid.uuid4(),
        ingestion_status="ready",
        ingestion_error=None,
        last_ingested_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
        screening_score=0.8,
        is_screened_in=True,
        screened_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
    )
    defaults.update(overrides)
    return UniverseConstituent(**defaults)


@pytest.mark.asyncio
async def test_seed_universe_returns_seeded_and_total_counts():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with patch("nivesh.market_universe.router.UniverseConstituentRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.seed.return_value = 50
        mock_repo.list_by_index.return_value = [_constituent_row() for _ in range(50)]
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/universe/seed")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["index_name"] == "NIFTY50"
    assert body["seeded"] == 50
    assert body["total_tracked"] == 50


@pytest.mark.asyncio
async def test_sync_universe_with_explicit_symbols_queues_only_those():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with (
        patch("nivesh.market_universe.router.UniverseConstituentRepository") as mock_repo_cls,
        patch("nivesh.market_universe.router.sync_universe_constituent") as mock_task,
    ):
        mock_repo_cls.return_value = AsyncMock()
        mock_task.delay.return_value = MagicMock(id="task-1")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/universe/sync", json={"symbols": ["tcs", "infy"]})

    app.dependency_overrides.clear()
    assert response.status_code == 202
    body = response.json()
    assert body["queued"] == ["TCS", "INFY"]
    assert mock_task.delay.call_count == 2


@pytest.mark.asyncio
async def test_sync_universe_without_symbols_queues_pending_and_failed():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with (
        patch("nivesh.market_universe.router.UniverseConstituentRepository") as mock_repo_cls,
        patch("nivesh.market_universe.router.sync_universe_constituent") as mock_task,
    ):
        mock_repo = AsyncMock()
        mock_repo.list_by_index.return_value = [
            _constituent_row(symbol="TCS", ingestion_status="pending"),
            _constituent_row(symbol="INFY", ingestion_status="failed"),
        ]
        mock_repo_cls.return_value = mock_repo
        mock_task.delay.return_value = MagicMock(id="task-1")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/universe/sync", json={})

    app.dependency_overrides.clear()
    assert response.status_code == 202
    body = response.json()
    assert set(body["queued"]) == {"TCS", "INFY"}
    mock_repo.list_by_index.assert_called_once_with("NIFTY50", statuses={"pending", "failed"})


@pytest.mark.asyncio
async def test_screen_universe_route_queues_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.market_universe.router.screen_universe") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-1")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/universe/screen", json={"top_n": 10})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["top_n"] == 10
    mock_task.delay.assert_called_once_with("NIFTY50", 10)


@pytest.mark.asyncio
async def test_list_universe_returns_tracked_constituents():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with patch("nivesh.market_universe.router.UniverseConstituentRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.list_by_index.return_value = [_constituent_row(symbol="TCS")]
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/universe")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "TCS"


@pytest.mark.asyncio
async def test_get_constituent_returns_404_for_unknown_symbol():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with patch("nivesh.market_universe.router.UniverseConstituentRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_symbol.return_value = None
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/universe/NOPE")

    app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["error"]["code"] == NotFoundError.error_code

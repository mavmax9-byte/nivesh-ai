import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.ai_agents.models import AgentFinding
from nivesh.ai_agents.router import get_ai_agents_service
from nivesh.core.exceptions import NotFoundError
from nivesh.main import create_app


def _finding_row(**overrides) -> AgentFinding:
    defaults = dict(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        agent_code="fundamental_analyst",
        result_json={"summary": "Revenue grew steadily.", "citations": []},
        prompt_version="fundamental-v1",
        model_used="gpt-4o-mini",
        confidence_score=0.6,
        evidence_sufficiency="sufficient",
    )
    defaults.update(overrides)
    row = AgentFinding(**defaults)
    row.created_at = datetime(2026, 7, 30, 4, 0, 0, tzinfo=UTC)
    row.updated_at = datetime(2026, 7, 30, 4, 0, 0, tzinfo=UTC)
    return row


@pytest.mark.asyncio
async def test_generate_fundamental_finding_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.ai_agents.router.generate_fundamental_analysis") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-999")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/fundamental/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-999"
    mock_task.delay.assert_called_once_with("TCS")


@pytest.mark.asyncio
async def test_get_fundamental_finding_returns_persisted_result():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_finding.return_value = _finding_row()
    app.dependency_overrides[get_ai_agents_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agents/fundamental/tcs")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_code"] == "fundamental_analyst"
    assert body["evidence_sufficiency"] == "sufficient"
    assert body["result_json"]["summary"] == "Revenue grew steadily."
    mock_service.get_latest_finding.assert_awaited_once_with("tcs")


@pytest.mark.asyncio
async def test_get_fundamental_finding_returns_404_when_none_exists():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_finding.return_value = None
    app.dependency_overrides[get_ai_agents_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agents/fundamental/tcs")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_fundamental_finding_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_finding.side_effect = NotFoundError(
        "No company found with symbol 'NOPE'"
    )
    app.dependency_overrides[get_ai_agents_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agents/fundamental/NOPE")

    assert response.status_code == 404

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.ai_agents.models import AgentFinding
from nivesh.ai_agents.router import get_ai_agents_service, get_technical_service
from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.main import create_app


async def _fake_get_db():
    yield MagicMock()


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


@pytest.mark.asyncio
async def test_generate_technical_finding_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.ai_agents.router.generate_technical_analysis") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-111")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents/technical/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["task_id"] == "task-111"
    mock_task.delay.assert_called_once_with("TCS")


@pytest.mark.asyncio
async def test_get_technical_finding_returns_persisted_result():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_latest_finding.return_value = _finding_row(agent_code="technical_analyst")
    app.dependency_overrides[get_technical_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agents/technical/tcs")

    assert response.status_code == 200
    assert response.json()["agent_code"] == "technical_analyst"


@pytest.mark.asyncio
async def test_request_analysis_enqueues_committee_task_and_returns_202():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    company_id = uuid.uuid4()
    company = MagicMock()
    company.symbol = "TCS"

    with (
        patch("nivesh.ai_agents.router.CompanyRepository") as mock_repo_cls,
        patch("nivesh.ai_agents.router.run_investment_committee") as mock_task,
    ):
        mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=company)
        mock_task.delay.return_value = MagicMock(id=str(uuid.uuid4()))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/reports", json={"company_id": str(company_id)})

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    mock_task.delay.assert_called_once_with("TCS")


@pytest.mark.asyncio
async def test_request_analysis_returns_404_for_unknown_company_id():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    with patch("nivesh.ai_agents.router.CompanyRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/reports", json={"company_id": str(uuid.uuid4())})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_committee_report_returns_404_when_no_decision_exists():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    company = MagicMock()
    company.id = uuid.uuid4()
    company.symbol = "TCS"

    with (
        patch("nivesh.ai_agents.router.CompanyRepository") as mock_company_repo_cls,
        patch("nivesh.ai_agents.router.AgentFindingRepository") as mock_finding_repo_cls,
    ):
        mock_company_repo_cls.return_value.get_by_symbol = AsyncMock(return_value=company)
        mock_finding_repo_cls.return_value.get_latest = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/reports/tcs")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_committee_report_returns_404_when_rejected_by_compliance():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    company = MagicMock()
    company.id = uuid.uuid4()
    company.symbol = "TCS"

    decision_row = _finding_row(agent_code="investment_committee")
    compliance_row = _finding_row(
        agent_code="compliance_review", result_json={"approved": False, "reasons": ["x"]}
    )

    async def _get_latest(company_id, agent_code):
        return {"investment_committee": decision_row, "compliance_review": compliance_row}.get(
            agent_code
        )

    with (
        patch("nivesh.ai_agents.router.CompanyRepository") as mock_company_repo_cls,
        patch("nivesh.ai_agents.router.AgentFindingRepository") as mock_finding_repo_cls,
    ):
        mock_company_repo_cls.return_value.get_by_symbol = AsyncMock(return_value=company)
        mock_finding_repo_cls.return_value.get_latest = _get_latest

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/reports/tcs")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_committee_report_returns_approved_decision():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    company = MagicMock()
    company.id = uuid.uuid4()
    company.symbol = "TCS"

    decision_row = _finding_row(
        agent_code="investment_committee",
        result_json={"summary": "Overall steady.", "citations": []},
    )
    compliance_row = _finding_row(
        agent_code="compliance_review", result_json={"approved": True, "reasons": []}
    )

    async def _get_latest(company_id, agent_code):
        return {"investment_committee": decision_row, "compliance_review": compliance_row}.get(
            agent_code
        )

    with (
        patch("nivesh.ai_agents.router.CompanyRepository") as mock_company_repo_cls,
        patch("nivesh.ai_agents.router.AgentFindingRepository") as mock_finding_repo_cls,
    ):
        mock_company_repo_cls.return_value.get_by_symbol = AsyncMock(return_value=company)
        mock_finding_repo_cls.return_value.get_latest = _get_latest

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/reports/tcs")

    assert response.status_code == 200
    body = response.json()
    assert body["result_json"]["summary"] == "Overall steady."
    assert body["compliance"]["approved"] is True

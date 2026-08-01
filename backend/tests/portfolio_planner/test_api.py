import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.main import create_app
from nivesh.portfolio_planner.models import PlannedPortfolio, PlannedPortfolioHolding


async def _fake_get_db():
    yield MagicMock()


def _portfolio_row(status: str = "ready", **overrides) -> PlannedPortfolio:
    defaults = dict(
        id=uuid.uuid4(),
        capital=100000.0,
        risk_profile="balanced",
        horizon="medium",
        sector_exclusions=[],
        status=status,
        summary="One holding in Technology." if status == "ready" else None,
        caveats=[],
        unallocated_amount=80000.0 if status == "ready" else None,
        confidence_score=0.7 if status == "ready" else None,
        evidence_sufficiency="sufficient" if status == "ready" else None,
        universe_size=1 if status == "ready" else None,
        failure_reason="No eligible companies." if status == "failed" else None,
    )
    defaults.update(overrides)
    row = PlannedPortfolio(**defaults)
    row.created_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    row.updated_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    row.holdings = defaults.get("holdings", [])
    return row


def _holding_row(**overrides) -> PlannedPortfolioHolding:
    defaults = dict(
        id=uuid.uuid4(),
        portfolio_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        symbol="TCS",
        company_name="Tata Consultancy Services",
        sector="Technology",
        allocated_amount=20000.0,
        allocated_weight=0.2,
        rank_score=0.75,
        confidence_score=0.7,
        evidence_sufficiency="sufficient",
        thesis="Solid fundamentals.",
        weight_rationale="Allocated 20% based on composite score.",
        top_citation_title="Quarterly statement",
        top_citation_source_type="financial_statement",
    )
    defaults.update(overrides)
    row = PlannedPortfolioHolding(**defaults)
    row.created_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    return row


@pytest.mark.asyncio
async def test_create_planned_portfolio_enqueues_celery_task_and_returns_202():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with (
        patch("nivesh.portfolio_planner.router.PlannedPortfolioRepository") as mock_repo_cls,
        patch("nivesh.portfolio_planner.router.generate_planned_portfolio") as mock_task,
    ):
        mock_repo = AsyncMock()
        mock_repo.create_generating.return_value = _portfolio_row(status="generating")
        mock_repo_cls.return_value = mock_repo
        mock_task.delay.return_value = MagicMock(id="task-1")

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/planner/portfolios",
                json={
                    "capital": 100000,
                    "risk_profile": "balanced",
                    "horizon": "medium",
                    "sector_exclusions": [],
                },
            )

    app.dependency_overrides.clear()
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "generating"
    mock_repo.create_generating.assert_called_once_with(
        capital=100000.0, risk_profile="balanced", horizon="medium", sector_exclusions=[]
    )
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_create_planned_portfolio_rejects_non_positive_capital():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/planner/portfolios",
            json={"capital": 0, "risk_profile": "balanced", "horizon": "medium"},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_planned_portfolio_returns_ready_portfolio_with_holdings():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    portfolio = _portfolio_row(status="ready", holdings=[_holding_row()])

    with patch("nivesh.portfolio_planner.router.PlannedPortfolioRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = portfolio
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/planner/portfolios/{portfolio.id}")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert len(body["holdings"]) == 1
    assert body["holdings"][0]["symbol"] == "TCS"
    assert body["unallocated_amount"] == pytest.approx(80000.0)


@pytest.mark.asyncio
async def test_get_planned_portfolio_returns_404_for_unknown_id():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with patch("nivesh.portfolio_planner.router.PlannedPortfolioRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/planner/portfolios/{uuid.uuid4()}")

    app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["error"]["code"] == NotFoundError.error_code


@pytest.mark.asyncio
async def test_get_planned_portfolio_surfaces_failed_status_and_reason():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    portfolio = _portfolio_row(status="failed")

    with patch("nivesh.portfolio_planner.router.PlannedPortfolioRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = portfolio
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/planner/portfolios/{portfolio.id}")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["failure_reason"] == "No eligible companies."


@pytest.mark.asyncio
async def test_rebalance_placeholder_returns_not_available_for_a_real_portfolio():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    portfolio = _portfolio_row(status="ready")

    with patch("nivesh.portfolio_planner.router.PlannedPortfolioRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = portfolio
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/planner/portfolios/{portfolio.id}/rebalance")

    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "not yet available" in body["message"]


@pytest.mark.asyncio
async def test_rebalance_placeholder_still_404s_for_unknown_portfolio():
    app = create_app()
    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)

    with patch("nivesh.portfolio_planner.router.PlannedPortfolioRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_cls.return_value = mock_repo

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/planner/portfolios/{uuid.uuid4()}/rebalance")

    app.dependency_overrides.clear()
    assert response.status_code == 404

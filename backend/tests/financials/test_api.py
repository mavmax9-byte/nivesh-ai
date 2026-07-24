from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.financials.models import (
    BalanceSheet,
    CashFlowStatement,
    FinancialRatio,
    FinancialStatement,
    ProfitAndLoss,
)
from nivesh.financials.router import get_financial_statement_service
from nivesh.financials.service import FinancialsOverview
from nivesh.main import create_app


def _full_statement(**overrides) -> FinancialStatement:
    defaults = dict(
        id=uuid4(),
        company_id=uuid4(),
        period_type="annual",
        fiscal_year=2026,
        fiscal_period="FY",
        period_end_date=date(2026, 3, 31),
        currency="INR",
        version=1,
        source="yfinance",
    )
    defaults.update(overrides)
    statement = FinancialStatement(**defaults)
    statement.created_at = datetime(2026, 5, 1, 10, 0, 0)
    statement.balance_sheet = BalanceSheet(
        total_assets=Decimal("1000.00"),
        current_assets=Decimal("400.00"),
        non_current_assets=Decimal("600.00"),
        total_liabilities=Decimal("600.00"),
        current_liabilities=Decimal("250.00"),
        non_current_liabilities=Decimal("350.00"),
        total_equity=Decimal("400.00"),
        share_capital=Decimal("50.00"),
        reserves_and_surplus=Decimal("350.00"),
        total_debt=Decimal("300.00"),
        cash_and_equivalents=Decimal("150.00"),
    )
    statement.profit_and_loss = ProfitAndLoss(
        total_revenue=Decimal("500.00"),
        cost_of_revenue=Decimal("300.00"),
        gross_profit=Decimal("200.00"),
        operating_expenses=Decimal("80.00"),
        operating_income=Decimal("120.00"),
        interest_expense=Decimal("20.00"),
        tax_expense=Decimal("20.00"),
        net_income=Decimal("80.00"),
        eps_basic=Decimal("12.50"),
        eps_diluted=Decimal("12.30"),
    )
    statement.cash_flow = CashFlowStatement(
        operating_cash_flow=Decimal("150.00"),
        investing_cash_flow=Decimal("-60.00"),
        financing_cash_flow=Decimal("-40.00"),
        capital_expenditure=Decimal("-40.00"),
        net_change_in_cash=Decimal("50.00"),
        free_cash_flow=Decimal("110.00"),
    )
    statement.quarterly_result = None
    statement.ratio = FinancialRatio(
        current_ratio=Decimal("1.6000"),
        debt_to_equity=Decimal("0.7500"),
        net_profit_margin=Decimal("16.0000"),
        operating_margin=Decimal("24.0000"),
        return_on_equity=Decimal("20.0000"),
        return_on_assets=Decimal("8.0000"),
        asset_turnover=Decimal("0.5000"),
        interest_coverage_ratio=Decimal("6.0000"),
    )
    return statement


@pytest.mark.asyncio
async def test_get_financials_overview_returns_latest_annual_and_quarterly():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_overview.return_value = FinancialsOverview(
        symbol="TCS",
        latest_annual=_full_statement(),
        latest_quarterly=_full_statement(period_type="quarterly", fiscal_period="Q4"),
    )
    app.dependency_overrides[get_financial_statement_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/financials/tcs")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["latest_annual"]["fiscal_period"] == "FY"
    assert float(body["latest_annual"]["balance_sheet"]["total_assets"]) == 1000.00
    assert float(body["latest_annual"]["ratio"]["current_ratio"]) == 1.6
    assert body["latest_quarterly"]["fiscal_period"] == "Q4"


@pytest.mark.asyncio
async def test_get_financials_overview_returns_404_when_no_company():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_overview.side_effect = NotFoundError("No company found with symbol 'NOPE'")
    app.dependency_overrides[get_financial_statement_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/financials/NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_annual_financials_returns_statement_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_annual_statements.return_value = [
        _full_statement(fiscal_year=2026),
        _full_statement(fiscal_year=2025),
    ]
    app.dependency_overrides[get_financial_statement_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/financials/tcs/annual")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["fiscal_year"] == 2026
    assert body[1]["fiscal_year"] == 2025
    mock_service.get_annual_statements.assert_awaited_once_with("tcs", limit=8)


@pytest.mark.asyncio
async def test_get_quarterly_financials_returns_statement_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_quarterly_statements.return_value = [
        _full_statement(period_type="quarterly", fiscal_period="Q2")
    ]
    app.dependency_overrides[get_financial_statement_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/financials/tcs/quarterly?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["period_type"] == "quarterly"
    mock_service.get_quarterly_statements.assert_awaited_once_with("tcs", limit=5)


@pytest.mark.asyncio
async def test_sync_financials_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.financials.router.sync_company_financials") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-456")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/financials/sync/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-456"
    mock_task.delay.assert_called_once_with("TCS")

"""Repository tests against a real PostgreSQL test database.

Exercises the aggregate-root write sequence (statement -> balance sheet ->
P&L -> cash flow -> commit) and the versioned/latest-period read paths the
service and API depend on.
"""

from datetime import date
from decimal import Decimal

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.financials.repository import FinancialStatementRepository


async def _make_company(db_session, symbol: str = "TCS"):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    exchange = await exchange_repository.get_or_create_by_code("NSE")
    return await company_repository.upsert(
        symbol=symbol,
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )


def _balance_sheet_data(**overrides) -> dict:
    defaults = dict(
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
    defaults.update(overrides)
    return defaults


def _profit_and_loss_data(**overrides) -> dict:
    defaults = dict(
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
    defaults.update(overrides)
    return defaults


def _cash_flow_data(**overrides) -> dict:
    defaults = dict(
        operating_cash_flow=Decimal("150.00"),
        investing_cash_flow=Decimal("-60.00"),
        financing_cash_flow=Decimal("-40.00"),
        capital_expenditure=Decimal("-40.00"),
        net_change_in_cash=Decimal("50.00"),
        free_cash_flow=Decimal("110.00"),
    )
    defaults.update(overrides)
    return defaults


async def _write_full_statement(
    repository: FinancialStatementRepository,
    company_id,
    *,
    period_type: str = "annual",
    fiscal_year: int = 2026,
    fiscal_period: str = "FY",
    period_end_date: date = date(2026, 3, 31),
    version: int = 1,
    total_assets: Decimal = Decimal("1000.00"),
):
    statement = await repository.create_statement(
        company_id=company_id,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_end_date=period_end_date,
        currency="INR",
        version=version,
        source="yfinance",
    )
    await repository.create_balance_sheet(
        statement.id, _balance_sheet_data(total_assets=total_assets)
    )
    await repository.create_profit_and_loss(statement.id, _profit_and_loss_data())
    await repository.create_cash_flow(statement.id, _cash_flow_data())
    await repository.create_financial_ratio(
        statement.id,
        {
            "current_ratio": Decimal("1.6"),
            "debt_to_equity": Decimal("0.75"),
            "net_profit_margin": Decimal("16.0"),
            "operating_margin": Decimal("24.0"),
            "return_on_equity": Decimal("20.0"),
            "return_on_assets": Decimal("8.0"),
            "asset_turnover": Decimal("0.5"),
            "interest_coverage_ratio": Decimal("6.0"),
        },
    )
    return await repository.commit_statement(statement)


@pytest.mark.asyncio
async def test_create_statement_persists_full_aggregate(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    statement = await _write_full_statement(repository, company.id)

    assert statement.version == 1
    assert statement.balance_sheet.total_assets == Decimal("1000.00")
    assert statement.profit_and_loss.net_income == Decimal("80.00")
    assert statement.cash_flow.operating_cash_flow == Decimal("150.00")
    assert statement.ratio.current_ratio == Decimal("1.6")


@pytest.mark.asyncio
async def test_get_latest_statement_returns_highest_version(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    await _write_full_statement(repository, company.id, version=1, total_assets=Decimal("1000.00"))
    await _write_full_statement(repository, company.id, version=2, total_assets=Decimal("1050.00"))

    latest = await repository.get_latest_statement(company.id, "annual", 2026, "FY")
    assert latest.version == 2
    assert latest.balance_sheet.total_assets == Decimal("1050.00")


@pytest.mark.asyncio
async def test_get_latest_statement_returns_none_when_no_statement_exists(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    latest = await repository.get_latest_statement(company.id, "annual", 2026, "FY")
    assert latest is None


@pytest.mark.asyncio
async def test_list_latest_statements_returns_one_row_per_period_at_highest_version(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    await _write_full_statement(
        repository,
        company.id,
        fiscal_year=2025,
        period_end_date=date(2025, 3, 31),
        version=1,
        total_assets=Decimal("900.00"),
    )
    await _write_full_statement(
        repository,
        company.id,
        fiscal_year=2026,
        period_end_date=date(2026, 3, 31),
        version=1,
        total_assets=Decimal("1000.00"),
    )
    # A restatement of the 2026 period -- version 2 should be the one returned.
    await _write_full_statement(
        repository,
        company.id,
        fiscal_year=2026,
        period_end_date=date(2026, 3, 31),
        version=2,
        total_assets=Decimal("1010.00"),
    )

    statements = await repository.list_latest_statements(company.id, "annual", limit=8)

    assert [s.fiscal_year for s in statements] == [2026, 2025]
    assert statements[0].version == 2
    assert statements[0].balance_sheet.total_assets == Decimal("1010.00")


@pytest.mark.asyncio
async def test_list_latest_statements_respects_limit(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    for year in (2024, 2025, 2026):
        await _write_full_statement(
            repository, company.id, fiscal_year=year, period_end_date=date(year, 3, 31)
        )

    statements = await repository.list_latest_statements(company.id, "annual", limit=2)
    assert len(statements) == 2
    assert statements[0].fiscal_year == 2026
    assert statements[1].fiscal_year == 2025


@pytest.mark.asyncio
async def test_get_latest_statement_before_finds_prior_quarter(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    await _write_full_statement(
        repository,
        company.id,
        period_type="quarterly",
        fiscal_year=2026,
        fiscal_period="Q1",
        period_end_date=date(2026, 6, 30),
    )
    await _write_full_statement(
        repository,
        company.id,
        period_type="quarterly",
        fiscal_year=2026,
        fiscal_period="Q2",
        period_end_date=date(2026, 9, 30),
    )

    previous = await repository.get_latest_statement_before(
        company.id, "quarterly", date(2026, 9, 30)
    )
    assert previous is not None
    assert previous.fiscal_period == "Q1"
    assert previous.profit_and_loss.net_income == Decimal("80.00")


@pytest.mark.asyncio
async def test_get_latest_statement_before_returns_none_when_no_prior_period(db_session):
    company = await _make_company(db_session)
    repository = FinancialStatementRepository(db_session)

    await _write_full_statement(
        repository,
        company.id,
        period_type="quarterly",
        fiscal_year=2026,
        fiscal_period="Q1",
        period_end_date=date(2026, 6, 30),
    )

    previous = await repository.get_latest_statement_before(
        company.id, "quarterly", date(2026, 6, 30)
    )
    assert previous is None

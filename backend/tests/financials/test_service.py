from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.financials.models import (
    BalanceSheet,
    CashFlowStatement,
    FinancialStatement,
    ProfitAndLoss,
)
from nivesh.financials.providers.base import (
    ProviderBalanceSheet,
    ProviderCashFlow,
    ProviderFinancialStatement,
    ProviderProfitAndLoss,
)
from nivesh.financials.service import FinancialStatementService
from nivesh.financials.validation import InvalidFinancialDataError
from nivesh.research.models import CompanyResearchDossier, ResearchVersion


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


def _provider_statement(**overrides) -> ProviderFinancialStatement:
    defaults: dict = dict(
        symbol="TCS",
        period_type="annual",
        fiscal_year=2026,
        fiscal_period="FY",
        period_end_date=date(2026, 3, 31),
        currency="INR",
        balance_sheet=ProviderBalanceSheet(
            total_assets=Decimal("1000"),
            current_assets=Decimal("400"),
            non_current_assets=Decimal("600"),
            total_liabilities=Decimal("600"),
            current_liabilities=Decimal("250"),
            non_current_liabilities=Decimal("350"),
            total_equity=Decimal("400"),
            share_capital=Decimal("50"),
            reserves_and_surplus=Decimal("350"),
            total_debt=Decimal("300"),
            cash_and_equivalents=Decimal("150"),
        ),
        profit_and_loss=ProviderProfitAndLoss(
            total_revenue=Decimal("500"),
            cost_of_revenue=Decimal("300"),
            gross_profit=Decimal("200"),
            operating_expenses=Decimal("80"),
            operating_income=Decimal("120"),
            interest_expense=Decimal("20"),
            tax_expense=Decimal("20"),
            net_income=Decimal("80"),
            eps_basic=Decimal("12.5"),
            eps_diluted=Decimal("12.3"),
        ),
        cash_flow=ProviderCashFlow(
            operating_cash_flow=Decimal("150"),
            investing_cash_flow=Decimal("-60"),
            financing_cash_flow=Decimal("-40"),
            capital_expenditure=Decimal("-40"),
            net_change_in_cash=Decimal("50"),
        ),
    )
    defaults.update(overrides)
    return ProviderFinancialStatement(**defaults)


def _stored_signature(*, total_assets: Decimal = Decimal("1000")) -> tuple:
    """Balance sheet / P&L / cash flow stand-ins with the same field names
    as the ORM rows, matching what `_provider_statement()`'s figures
    normalize to -- used to test duplicate-vs-changed detection without a
    database."""
    balance_sheet = BalanceSheet(
        total_assets=total_assets,
        current_assets=Decimal("400"),
        non_current_assets=Decimal("600"),
        total_liabilities=Decimal("600"),
        current_liabilities=Decimal("250"),
        non_current_liabilities=Decimal("350"),
        total_equity=Decimal("400"),
        share_capital=Decimal("50"),
        reserves_and_surplus=Decimal("350"),
        total_debt=Decimal("300"),
        cash_and_equivalents=Decimal("150"),
    )
    profit_and_loss = ProfitAndLoss(
        total_revenue=Decimal("500"),
        cost_of_revenue=Decimal("300"),
        gross_profit=Decimal("200"),
        operating_expenses=Decimal("80"),
        operating_income=Decimal("120"),
        interest_expense=Decimal("20"),
        tax_expense=Decimal("20"),
        net_income=Decimal("80"),
        eps_basic=Decimal("12.5"),
        eps_diluted=Decimal("12.3"),
    )
    cash_flow = CashFlowStatement(
        operating_cash_flow=Decimal("150"),
        investing_cash_flow=Decimal("-60"),
        financing_cash_flow=Decimal("-40"),
        capital_expenditure=Decimal("-40"),
        net_change_in_cash=Decimal("50"),
        free_cash_flow=Decimal("110"),
    )
    return balance_sheet, profit_and_loss, cash_flow


def _stored_statement_stub(
    *,
    fiscal_year: int = 2026,
    fiscal_period: str = "FY",
    period_end_date: date = date(2026, 3, 31),
    period_type: str = "annual",
    version: int = 1,
) -> FinancialStatement:
    statement = FinancialStatement(
        id=uuid4(),
        company_id=uuid4(),
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_end_date=period_end_date,
        currency="INR",
        version=version,
        source="yfinance",
    )
    return statement


def _make_service(
    company,
    *,
    get_latest_statement=None,
    get_latest_statement_before=None,
    latest_research_version=None,
):
    provider = AsyncMock()

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    statement_repository = AsyncMock()
    if get_latest_statement is not None:
        statement_repository.get_latest_statement.side_effect = get_latest_statement
    else:
        statement_repository.get_latest_statement.return_value = None
    statement_repository.get_latest_statement_before.return_value = get_latest_statement_before
    statement_repository.create_statement.side_effect = lambda **kwargs: FinancialStatement(
        id=uuid4(), **kwargs
    )
    statement_repository.commit_statement.side_effect = lambda statement: statement

    dossier_repository = AsyncMock()
    dossier_repository.get_or_create_dossier.return_value = CompanyResearchDossier(
        id=uuid4(), company_id=company.id
    )
    dossier_repository.get_latest_version.return_value = latest_research_version

    service = FinancialStatementService(
        provider=provider,
        company_repository=company_repository,
        statement_repository=statement_repository,
        dossier_repository=dossier_repository,
    )
    return service, provider, statement_repository, dossier_repository


@pytest.mark.asyncio
async def test_sync_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None

    service = FinancialStatementService(
        provider=AsyncMock(),
        company_repository=company_repository,
        statement_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.sync_company_financials("NOPE")


@pytest.mark.asyncio
async def test_sync_creates_new_statement_and_computes_ratio():
    company = _company()
    version = ResearchVersion(id=uuid4(), dossier_id=uuid4(), version_number=1)
    service, provider, statement_repository, dossier_repository = _make_service(
        company, latest_research_version=version
    )
    provider.get_annual_statements.return_value = [_provider_statement()]
    provider.get_quarterly_statements.return_value = []

    result = await service.sync_company_financials("TCS")

    assert result.statements_synced == 1
    assert result.statements_unchanged == 0

    statement_repository.create_statement.assert_awaited_once()
    _, create_kwargs = statement_repository.create_statement.await_args
    assert create_kwargs["version"] == 1
    assert create_kwargs["period_type"] == "annual"

    statement_repository.create_balance_sheet.assert_awaited_once()
    statement_repository.create_profit_and_loss.assert_awaited_once()
    statement_repository.create_cash_flow.assert_awaited_once()
    statement_repository.create_quarterly_result.assert_not_awaited()

    statement_repository.create_financial_ratio.assert_awaited_once()
    _, ratio_data = statement_repository.create_financial_ratio.await_args.args
    assert ratio_data["current_ratio"] == Decimal("1.6000")  # 400 / 250
    assert ratio_data["debt_to_equity"] == Decimal("0.7500")  # 300 / 400
    assert ratio_data["net_profit_margin"] == Decimal("16.0000")  # 80 / 500 * 100
    assert ratio_data["return_on_equity"] == Decimal("20.0000")  # 80 / 400 * 100

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert len(source_rows) == 1
    assert source_rows[0]["source_type"] == "financial_data"
    assert source_rows[0]["version_id"] == version.id

    dossier_repository.create_timeline_event.assert_awaited_once()
    statement_repository.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_skips_unchanged_statement():
    company = _company()
    existing = _stored_statement_stub(version=1)
    existing.balance_sheet, existing.profit_and_loss, existing.cash_flow = _stored_signature()

    async def get_latest_statement(company_id, period_type, fiscal_year, fiscal_period):
        return existing

    service, provider, statement_repository, dossier_repository = _make_service(
        company, get_latest_statement=get_latest_statement
    )
    provider.get_annual_statements.return_value = [_provider_statement()]
    provider.get_quarterly_statements.return_value = []

    result = await service.sync_company_financials("TCS")

    assert result.statements_synced == 0
    assert result.statements_unchanged == 1
    statement_repository.create_statement.assert_not_awaited()
    dossier_repository.get_or_create_dossier.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_creates_next_version_when_figures_changed():
    company = _company()
    existing = _stored_statement_stub(version=1)
    existing.balance_sheet, existing.profit_and_loss, existing.cash_flow = _stored_signature(
        total_assets=Decimal("900")  # differs from _provider_statement()'s 1000
    )

    async def get_latest_statement(company_id, period_type, fiscal_year, fiscal_period):
        return existing

    service, provider, statement_repository, dossier_repository = _make_service(
        company, get_latest_statement=get_latest_statement, latest_research_version=None
    )
    provider.get_annual_statements.return_value = [_provider_statement()]
    provider.get_quarterly_statements.return_value = []

    result = await service.sync_company_financials("TCS")

    assert result.statements_synced == 1
    _, create_kwargs = statement_repository.create_statement.await_args
    assert create_kwargs["version"] == 2


@pytest.mark.asyncio
async def test_sync_treats_statement_with_missing_stored_children_as_changed():
    """A statement row that somehow lacks its balance sheet/P&L/cash flow
    children (e.g. a previous partial write) must never be treated as an
    unchanged duplicate -- there is nothing to compare against."""
    company = _company()
    existing = _stored_statement_stub(version=1)
    existing.balance_sheet = None
    existing.profit_and_loss = None
    existing.cash_flow = None

    async def get_latest_statement(company_id, period_type, fiscal_year, fiscal_period):
        return existing

    service, provider, statement_repository, dossier_repository = _make_service(
        company, get_latest_statement=get_latest_statement, latest_research_version=None
    )
    provider.get_annual_statements.return_value = [_provider_statement()]
    provider.get_quarterly_statements.return_value = []

    result = await service.sync_company_financials("TCS")

    assert result.statements_synced == 1
    _, create_kwargs = statement_repository.create_statement.await_args
    assert create_kwargs["version"] == 2


@pytest.mark.asyncio
async def test_sync_rejects_statement_failing_accounting_equation():
    company = _company()
    unbalanced = _provider_statement(
        balance_sheet=ProviderBalanceSheet(
            total_assets=Decimal("1000"),
            current_assets=None,
            non_current_assets=None,
            total_liabilities=Decimal("100"),
            current_liabilities=None,
            non_current_liabilities=None,
            total_equity=Decimal("100"),
            share_capital=None,
            reserves_and_surplus=None,
            total_debt=None,
            cash_and_equivalents=None,
        )
    )
    service, provider, statement_repository, _ = _make_service(company)
    provider.get_annual_statements.return_value = [unbalanced]
    provider.get_quarterly_statements.return_value = []

    with pytest.raises(InvalidFinancialDataError):
        await service.sync_company_financials("TCS")

    statement_repository.create_statement.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_does_not_attach_evidence_when_no_research_version_exists_yet():
    company = _company()
    service, provider, statement_repository, dossier_repository = _make_service(
        company, latest_research_version=None
    )
    provider.get_annual_statements.return_value = [_provider_statement()]
    provider.get_quarterly_statements.return_value = []

    result = await service.sync_company_financials("TCS")

    assert result.statements_synced == 1
    dossier_repository.get_or_create_dossier.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()
    statement_repository.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_quarterly_result_computes_qoq_and_yoy_growth():
    company = _company()

    previous_quarter = FinancialStatement(id=uuid4())
    previous_quarter.profit_and_loss = ProfitAndLoss(
        total_revenue=Decimal("500"), net_income=Decimal("60")
    )
    same_quarter_last_year = FinancialStatement(id=uuid4())
    same_quarter_last_year.profit_and_loss = ProfitAndLoss(
        total_revenue=Decimal("440"), net_income=Decimal("90")
    )

    async def get_latest_statement(company_id, period_type, fiscal_year, fiscal_period):
        if fiscal_year == 2025:
            return same_quarter_last_year
        return None

    service, provider, statement_repository, dossier_repository = _make_service(
        company,
        get_latest_statement=get_latest_statement,
        get_latest_statement_before=previous_quarter,
    )
    quarterly_statement = _provider_statement(
        period_type="quarterly",
        fiscal_year=2026,
        fiscal_period="Q2",
        period_end_date=date(2026, 9, 30),
        profit_and_loss=ProviderProfitAndLoss(
            total_revenue=Decimal("550"),
            cost_of_revenue=Decimal("300"),
            gross_profit=Decimal("250"),
            operating_expenses=Decimal("100"),
            operating_income=Decimal("150"),
            interest_expense=Decimal("20"),
            tax_expense=Decimal("30"),
            net_income=Decimal("90"),
            eps_basic=Decimal("14.0"),
            eps_diluted=Decimal("13.8"),
        ),
    )
    provider.get_annual_statements.return_value = []
    provider.get_quarterly_statements.return_value = [quarterly_statement]

    await service.sync_company_financials("TCS")

    statement_repository.create_quarterly_result.assert_awaited_once()
    _, quarterly_data = statement_repository.create_quarterly_result.await_args.args
    assert quarterly_data["qoq_revenue_growth_pct"] == Decimal("10.0000")
    assert quarterly_data["yoy_revenue_growth_pct"] == Decimal("25.0000")
    assert quarterly_data["qoq_net_profit_growth_pct"] == Decimal("50.0000")
    assert quarterly_data["yoy_net_profit_growth_pct"] == Decimal("0.0000")

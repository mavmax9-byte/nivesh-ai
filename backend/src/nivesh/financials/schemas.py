"""Financial Statements Engine response schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class BalanceSheetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_assets: Decimal
    current_assets: Decimal | None
    non_current_assets: Decimal | None
    total_liabilities: Decimal
    current_liabilities: Decimal | None
    non_current_liabilities: Decimal | None
    total_equity: Decimal
    share_capital: Decimal | None
    reserves_and_surplus: Decimal | None
    total_debt: Decimal | None
    cash_and_equivalents: Decimal | None


class ProfitAndLossRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_revenue: Decimal
    cost_of_revenue: Decimal | None
    gross_profit: Decimal | None
    operating_expenses: Decimal | None
    operating_income: Decimal | None
    interest_expense: Decimal | None
    tax_expense: Decimal | None
    net_income: Decimal
    eps_basic: Decimal | None
    eps_diluted: Decimal | None


class CashFlowStatementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operating_cash_flow: Decimal
    investing_cash_flow: Decimal | None
    financing_cash_flow: Decimal | None
    capital_expenditure: Decimal | None
    net_change_in_cash: Decimal | None
    free_cash_flow: Decimal | None


class QuarterlyResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revenue: Decimal
    net_profit: Decimal
    eps: Decimal | None
    operating_margin: Decimal | None
    net_profit_margin: Decimal | None
    qoq_revenue_growth_pct: Decimal | None
    yoy_revenue_growth_pct: Decimal | None
    qoq_net_profit_growth_pct: Decimal | None
    yoy_net_profit_growth_pct: Decimal | None


class FinancialRatioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_ratio: Decimal | None
    debt_to_equity: Decimal | None
    net_profit_margin: Decimal | None
    operating_margin: Decimal | None
    return_on_equity: Decimal | None
    return_on_assets: Decimal | None
    asset_turnover: Decimal | None
    interest_coverage_ratio: Decimal | None


class FinancialStatementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_type: str
    fiscal_year: int
    fiscal_period: str
    period_end_date: date
    currency: str
    version: int
    source: str
    created_at: datetime
    balance_sheet: BalanceSheetRead | None
    profit_and_loss: ProfitAndLossRead | None
    cash_flow: CashFlowStatementRead | None
    quarterly_result: QuarterlyResultRead | None
    ratio: FinancialRatioRead | None


class FinancialsOverviewRead(BaseModel):
    symbol: str
    latest_annual: FinancialStatementRead | None
    latest_quarterly: FinancialStatementRead | None


class FinancialSyncResponse(BaseModel):
    symbol: str
    status: str
    task_id: str

"""Normalization of provider DTOs into repository-ready persistence payloads.

Pure functions -- no I/O, no side effects. Kept separate from the
repository (which only persists) and the service (which only orchestrates),
mirroring market_data/normalization.py's separation.
"""

import uuid

from nivesh.financials.providers.base import ProviderFinancialStatement

BALANCE_SHEET_FIELDS = (
    "total_assets",
    "current_assets",
    "non_current_assets",
    "total_liabilities",
    "current_liabilities",
    "non_current_liabilities",
    "total_equity",
    "share_capital",
    "reserves_and_surplus",
    "total_debt",
    "cash_and_equivalents",
)

PROFIT_AND_LOSS_FIELDS = (
    "total_revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "interest_expense",
    "tax_expense",
    "net_income",
    "eps_basic",
    "eps_diluted",
)

CASH_FLOW_FIELDS = (
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "capital_expenditure",
    "net_change_in_cash",
    "free_cash_flow",
)


def extract_fields(obj: dict | object, fields: tuple[str, ...]) -> dict:
    """Reads a fixed set of attributes off either a dict or an ORM row.

    Used to build comparable signatures for duplicate-statement detection,
    where one side is a freshly normalized dict and the other is an already
    persisted BalanceSheet/ProfitAndLoss/CashFlowStatement row.
    """
    if isinstance(obj, dict):
        return {field: obj.get(field) for field in fields}
    return {field: getattr(obj, field) for field in fields}


def normalize_statement(
    company_id: uuid.UUID, statement: ProviderFinancialStatement, source: str
) -> dict:
    return {
        "company_id": company_id,
        "period_type": statement.period_type,
        "fiscal_year": statement.fiscal_year,
        "fiscal_period": statement.fiscal_period,
        "period_end_date": statement.period_end_date,
        "currency": statement.currency,
        "source": source,
    }


def normalize_balance_sheet(statement: ProviderFinancialStatement) -> dict:
    bs = statement.balance_sheet
    return {
        "total_assets": bs.total_assets,
        "current_assets": bs.current_assets,
        "non_current_assets": bs.non_current_assets,
        "total_liabilities": bs.total_liabilities,
        "current_liabilities": bs.current_liabilities,
        "non_current_liabilities": bs.non_current_liabilities,
        "total_equity": bs.total_equity,
        "share_capital": bs.share_capital,
        "reserves_and_surplus": bs.reserves_and_surplus,
        "total_debt": bs.total_debt,
        "cash_and_equivalents": bs.cash_and_equivalents,
    }


def normalize_profit_and_loss(statement: ProviderFinancialStatement) -> dict:
    pl = statement.profit_and_loss
    return {
        "total_revenue": pl.total_revenue,
        "cost_of_revenue": pl.cost_of_revenue,
        "gross_profit": pl.gross_profit,
        "operating_expenses": pl.operating_expenses,
        "operating_income": pl.operating_income,
        "interest_expense": pl.interest_expense,
        "tax_expense": pl.tax_expense,
        "net_income": pl.net_income,
        "eps_basic": pl.eps_basic,
        "eps_diluted": pl.eps_diluted,
    }


def normalize_cash_flow(statement: ProviderFinancialStatement) -> dict:
    cf = statement.cash_flow
    free_cash_flow = None
    if cf.operating_cash_flow is not None and cf.capital_expenditure is not None:
        free_cash_flow = cf.operating_cash_flow - abs(cf.capital_expenditure)
    return {
        "operating_cash_flow": cf.operating_cash_flow,
        "investing_cash_flow": cf.investing_cash_flow,
        "financing_cash_flow": cf.financing_cash_flow,
        "capital_expenditure": cf.capital_expenditure,
        "net_change_in_cash": cf.net_change_in_cash,
        "free_cash_flow": free_cash_flow,
    }

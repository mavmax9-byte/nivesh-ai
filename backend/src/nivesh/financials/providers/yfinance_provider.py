"""Development financial statements provider, backed by Yahoo Finance via
yfinance.

Chosen for the same reasons as market_data/providers/yfinance_provider.py:
no API key, adequate coverage of NSE/BSE-listed equities, well-suited to
local development. Fully isolated behind `FinancialDataProvider` -- a
commercial or filings-based provider can replace it later without touching
`FinancialStatementService`.

yfinance's line-item row labels have shifted across releases, so every
field is looked up through a small set of known aliases and degrades to
None when none match, rather than raising. A missing line item is "not
reported by this provider," which validation.py -- not this module --
decides whether to reject.
"""

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import yfinance as yf

from nivesh.financials.models import (
    FISCAL_PERIOD_FULL_YEAR,
    PERIOD_TYPE_ANNUAL,
    PERIOD_TYPE_QUARTERLY,
)
from nivesh.financials.providers.base import (
    FinancialDataProvider,
    ProviderBalanceSheet,
    ProviderCashFlow,
    ProviderFinancialStatement,
    ProviderProfitAndLoss,
)
from nivesh.financials.providers.exceptions import (
    FinancialDataNotFoundError,
    FinancialProviderError,
)

_EXCHANGE_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_DEFAULT_EXCHANGE = "NSE"
_DEFAULT_CURRENCY = "INR"

# Candidate yfinance row labels for each canonical field, tried in order --
# see module docstring.
_BALANCE_SHEET_ALIASES: dict[str, tuple[str, ...]] = {
    "total_assets": ("Total Assets",),
    "current_assets": ("Current Assets",),
    "non_current_assets": ("Total Non Current Assets",),
    "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liab"),
    "current_liabilities": ("Current Liabilities",),
    "non_current_liabilities": (
        "Total Non Current Liabilities Net Minority Interest",
        "Total Non Current Liabilities",
    ),
    "total_equity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
    "share_capital": ("Common Stock", "Capital Stock"),
    "reserves_and_surplus": ("Retained Earnings",),
    "total_debt": ("Total Debt",),
    "cash_and_equivalents": (
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
    ),
}

_PROFIT_AND_LOSS_ALIASES: dict[str, tuple[str, ...]] = {
    "total_revenue": ("Total Revenue",),
    "cost_of_revenue": ("Cost Of Revenue", "Reconciled Cost Of Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_expenses": ("Operating Expense",),
    "operating_income": ("Operating Income",),
    "interest_expense": ("Interest Expense",),
    "tax_expense": ("Tax Provision",),
    "net_income": ("Net Income", "Net Income Common Stockholders"),
    "eps_basic": ("Basic EPS",),
    "eps_diluted": ("Diluted EPS",),
}

_CASH_FLOW_ALIASES: dict[str, tuple[str, ...]] = {
    "operating_cash_flow": (
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
    ),
    "investing_cash_flow": (
        "Investing Cash Flow",
        "Cash Flow From Continuing Investing Activities",
    ),
    "financing_cash_flow": (
        "Financing Cash Flow",
        "Cash Flow From Continuing Financing Activities",
    ),
    "capital_expenditure": ("Capital Expenditure",),
    "net_change_in_cash": ("Changes In Cash", "Changes In Cash Fiscal Year"),
}


def _to_yahoo_symbol(symbol: str, exchange_code: str = _DEFAULT_EXCHANGE) -> str:
    upper_symbol = symbol.upper()
    if any(upper_symbol.endswith(suffix) for suffix in _EXCHANGE_SUFFIX.values()):
        return upper_symbol
    suffix = _EXCHANGE_SUFFIX.get(exchange_code.upper(), _EXCHANGE_SUFFIX[_DEFAULT_EXCHANGE])
    return f"{upper_symbol}{suffix}"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return Decimal(str(round(float(value), 4)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _lookup(frame: pd.DataFrame, column: pd.Timestamp, aliases: tuple[str, ...]) -> Decimal | None:
    for label in aliases:
        if label in frame.index:
            return _to_decimal(frame.at[label, column])
    return None


def _fiscal_period_for_quarter(period_end_date: date) -> str:
    quarter = (period_end_date.month - 1) // 3 + 1
    return f"Q{quarter}"


def _build_statement(
    symbol: str,
    period_type: str,
    column: pd.Timestamp,
    balance_sheet_frame: pd.DataFrame,
    profit_and_loss_frame: pd.DataFrame,
    cash_flow_frame: pd.DataFrame,
    currency: str,
) -> ProviderFinancialStatement:
    period_end_date = column.date()
    fiscal_year = period_end_date.year
    fiscal_period = (
        FISCAL_PERIOD_FULL_YEAR
        if period_type == PERIOD_TYPE_ANNUAL
        else _fiscal_period_for_quarter(period_end_date)
    )

    balance_sheet = ProviderBalanceSheet(
        **{
            field: _lookup(balance_sheet_frame, column, aliases)
            for field, aliases in _BALANCE_SHEET_ALIASES.items()
        }
    )
    profit_and_loss = ProviderProfitAndLoss(
        **{
            field: _lookup(profit_and_loss_frame, column, aliases)
            for field, aliases in _PROFIT_AND_LOSS_ALIASES.items()
        }
    )
    cash_flow = ProviderCashFlow(
        **{
            field: _lookup(cash_flow_frame, column, aliases)
            for field, aliases in _CASH_FLOW_ALIASES.items()
        }
    )

    return ProviderFinancialStatement(
        symbol=symbol.upper(),
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        period_end_date=period_end_date,
        currency=currency,
        balance_sheet=balance_sheet,
        profit_and_loss=profit_and_loss,
        cash_flow=cash_flow,
    )


class YFinanceFinancialDataProvider(FinancialDataProvider):
    async def get_annual_statements(self, symbol: str) -> list[ProviderFinancialStatement]:
        return await asyncio.to_thread(self._fetch, symbol, PERIOD_TYPE_ANNUAL)

    async def get_quarterly_statements(self, symbol: str) -> list[ProviderFinancialStatement]:
        return await asyncio.to_thread(self._fetch, symbol, PERIOD_TYPE_QUARTERLY)

    def _fetch(self, symbol: str, period_type: str) -> list[ProviderFinancialStatement]:
        yahoo_symbol = _to_yahoo_symbol(symbol)
        ticker = yf.Ticker(yahoo_symbol)
        try:
            if period_type == PERIOD_TYPE_ANNUAL:
                balance_sheet_frame = ticker.balance_sheet
                profit_and_loss_frame = ticker.financials
                cash_flow_frame = ticker.cashflow
            else:
                balance_sheet_frame = ticker.quarterly_balance_sheet
                profit_and_loss_frame = ticker.quarterly_financials
                cash_flow_frame = ticker.quarterly_cashflow
            currency = (ticker.info or {}).get("financialCurrency") or _DEFAULT_CURRENCY
        except Exception as exc:
            raise FinancialProviderError(
                f"Financial statement fetch failed for '{symbol}': {exc}"
            ) from exc

        if balance_sheet_frame is None or balance_sheet_frame.empty:
            raise FinancialDataNotFoundError(
                f"No {period_type} financial statements found for symbol '{symbol}'"
            )

        columns = [
            column
            for column in balance_sheet_frame.columns
            if column in profit_and_loss_frame.columns and column in cash_flow_frame.columns
        ]
        if not columns:
            raise FinancialDataNotFoundError(
                f"No {period_type} financial statements found for symbol '{symbol}'"
            )

        statements = [
            _build_statement(
                symbol,
                period_type,
                column,
                balance_sheet_frame,
                profit_and_loss_frame,
                cash_flow_frame,
                currency,
            )
            for column in columns
        ]
        return sorted(statements, key=lambda s: s.period_end_date, reverse=True)

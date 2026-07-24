from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from nivesh.financials.providers.exceptions import FinancialDataNotFoundError
from nivesh.financials.providers.yfinance_provider import (
    YFinanceFinancialDataProvider,
    _fiscal_period_for_quarter,
    _to_decimal,
    _to_yahoo_symbol,
)


def _balance_sheet_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: {
                "Total Assets": 1000.0,
                "Current Assets": 400.0,
                "Total Liabilities Net Minority Interest": 600.0,
                "Current Liabilities": 250.0,
                "Stockholders Equity": 400.0,
                "Total Debt": 300.0,
                "Cash And Cash Equivalents": 150.0,
            }
            for column in columns
        }
    ).set_axis(
        [
            "Total Assets",
            "Current Assets",
            "Total Liabilities Net Minority Interest",
            "Current Liabilities",
            "Stockholders Equity",
            "Total Debt",
            "Cash And Cash Equivalents",
        ],
        axis=0,
    )


def _income_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: {
                "Total Revenue": 500.0,
                "Operating Income": 120.0,
                "Interest Expense": 20.0,
                "Net Income": 80.0,
                "Diluted EPS": 12.5,
            }
            for column in columns
        }
    ).set_axis(
        ["Total Revenue", "Operating Income", "Interest Expense", "Net Income", "Diluted EPS"],
        axis=0,
    )


def _cash_flow_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: {
                "Operating Cash Flow": 150.0,
                "Capital Expenditure": -40.0,
            }
            for column in columns
        }
    ).set_axis(["Operating Cash Flow", "Capital Expenditure"], axis=0)


def test_to_yahoo_symbol_defaults_to_nse():
    assert _to_yahoo_symbol("TCS") == "TCS.NS"


def test_to_decimal_handles_nan():
    assert _to_decimal(float("nan")) is None


def test_to_decimal_rounds_cleanly():
    assert _to_decimal(1234.56789) == Decimal("1234.5679")


def test_to_decimal_handles_none():
    assert _to_decimal(None) is None


def test_fiscal_period_for_quarter_maps_month_to_quarter():
    from datetime import date

    assert _fiscal_period_for_quarter(date(2026, 1, 15)) == "Q1"
    assert _fiscal_period_for_quarter(date(2026, 4, 15)) == "Q2"
    assert _fiscal_period_for_quarter(date(2026, 7, 15)) == "Q3"
    assert _fiscal_period_for_quarter(date(2026, 12, 15)) == "Q4"


@pytest.mark.asyncio
async def test_get_annual_statements_maps_frames_to_dtos():
    provider = YFinanceFinancialDataProvider()
    columns = pd.to_datetime(["2026-03-31", "2025-03-31"])

    mock_ticker = MagicMock()
    mock_ticker.balance_sheet = _balance_sheet_frame(columns)
    mock_ticker.financials = _income_frame(columns)
    mock_ticker.cashflow = _cash_flow_frame(columns)
    mock_ticker.info = {"financialCurrency": "INR"}

    with patch("nivesh.financials.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        statements = await provider.get_annual_statements("TCS")

    assert len(statements) == 2
    # Most recent period first.
    assert statements[0].period_end_date.isoformat() == "2026-03-31"
    assert statements[0].period_type == "annual"
    assert statements[0].fiscal_period == "FY"
    assert statements[0].fiscal_year == 2026
    assert statements[0].currency == "INR"

    balance_sheet = statements[0].balance_sheet
    assert balance_sheet.total_assets == Decimal("1000.0")
    assert balance_sheet.total_equity == Decimal("400.0")

    profit_and_loss = statements[0].profit_and_loss
    assert profit_and_loss.total_revenue == Decimal("500.0")
    assert profit_and_loss.net_income == Decimal("80.0")

    cash_flow = statements[0].cash_flow
    assert cash_flow.operating_cash_flow == Decimal("150.0")
    assert cash_flow.capital_expenditure == Decimal("-40.0")


@pytest.mark.asyncio
async def test_get_quarterly_statements_derive_quarter_from_period_end():
    provider = YFinanceFinancialDataProvider()
    columns = pd.to_datetime(["2026-06-30"])

    mock_ticker = MagicMock()
    mock_ticker.quarterly_balance_sheet = _balance_sheet_frame(columns)
    mock_ticker.quarterly_financials = _income_frame(columns)
    mock_ticker.quarterly_cashflow = _cash_flow_frame(columns)
    mock_ticker.info = {"financialCurrency": "INR"}

    with patch("nivesh.financials.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        statements = await provider.get_quarterly_statements("TCS")

    assert len(statements) == 1
    assert statements[0].period_type == "quarterly"
    assert statements[0].fiscal_period == "Q2"
    assert statements[0].fiscal_year == 2026


@pytest.mark.asyncio
async def test_missing_line_item_degrades_to_none_rather_than_raising():
    provider = YFinanceFinancialDataProvider()
    columns = pd.to_datetime(["2026-03-31"])

    mock_ticker = MagicMock()
    # Balance sheet frame missing "Total Debt" and "Cash And Cash Equivalents".
    partial_frame = pd.DataFrame(
        {columns[0]: {"Total Assets": 1000.0, "Stockholders Equity": 400.0}}
    )
    partial_frame.index = ["Total Assets", "Stockholders Equity"]
    mock_ticker.balance_sheet = partial_frame
    mock_ticker.financials = _income_frame(columns)
    mock_ticker.cashflow = _cash_flow_frame(columns)
    mock_ticker.info = {"financialCurrency": "INR"}

    with patch("nivesh.financials.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        statements = await provider.get_annual_statements("TCS")

    assert statements[0].balance_sheet.total_assets == Decimal("1000.0")
    assert statements[0].balance_sheet.total_debt is None
    assert statements[0].balance_sheet.cash_and_equivalents is None


@pytest.mark.asyncio
async def test_empty_balance_sheet_raises_financial_data_not_found():
    provider = YFinanceFinancialDataProvider()
    mock_ticker = MagicMock()
    mock_ticker.balance_sheet = pd.DataFrame()
    mock_ticker.financials = pd.DataFrame()
    mock_ticker.cashflow = pd.DataFrame()
    mock_ticker.info = {}

    with (
        patch("nivesh.financials.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker),
        pytest.raises(FinancialDataNotFoundError),
    ):
        await provider.get_annual_statements("NOPE")


@pytest.mark.asyncio
async def test_currency_defaults_to_inr_when_not_reported():
    provider = YFinanceFinancialDataProvider()
    columns = pd.to_datetime(["2026-03-31"])

    mock_ticker = MagicMock()
    mock_ticker.balance_sheet = _balance_sheet_frame(columns)
    mock_ticker.financials = _income_frame(columns)
    mock_ticker.cashflow = _cash_flow_frame(columns)
    mock_ticker.info = {}

    with patch("nivesh.financials.providers.yfinance_provider.yf.Ticker", return_value=mock_ticker):
        statements = await provider.get_annual_statements("TCS")

    assert statements[0].currency == "INR"

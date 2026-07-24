"""Provider factory -- the one place a concrete provider is chosen."""

from nivesh.financials.providers.base import FinancialDataProvider
from nivesh.financials.providers.yfinance_provider import YFinanceFinancialDataProvider


def get_financial_data_provider() -> FinancialDataProvider:
    return YFinanceFinancialDataProvider()

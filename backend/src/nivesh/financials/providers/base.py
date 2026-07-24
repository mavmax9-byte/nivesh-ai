"""Financial data provider interface.

Mirrors market_data/providers/base.py's adapter pattern: the application
depends only on `FinancialDataProvider`, never on a concrete provider. Every
provider (the development provider today, a filings- or commercial-data
provider later) returns these normalized DTOs, never raw provider payloads,
so swapping a provider never touches FinancialStatementService or anything
above it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class ProviderBalanceSheet:
    total_assets: Decimal | None
    current_assets: Decimal | None
    non_current_assets: Decimal | None
    total_liabilities: Decimal | None
    current_liabilities: Decimal | None
    non_current_liabilities: Decimal | None
    total_equity: Decimal | None
    share_capital: Decimal | None
    reserves_and_surplus: Decimal | None
    total_debt: Decimal | None
    cash_and_equivalents: Decimal | None


@dataclass(frozen=True)
class ProviderProfitAndLoss:
    total_revenue: Decimal | None
    cost_of_revenue: Decimal | None
    gross_profit: Decimal | None
    operating_expenses: Decimal | None
    operating_income: Decimal | None
    interest_expense: Decimal | None
    tax_expense: Decimal | None
    net_income: Decimal | None
    eps_basic: Decimal | None
    eps_diluted: Decimal | None


@dataclass(frozen=True)
class ProviderCashFlow:
    operating_cash_flow: Decimal | None
    investing_cash_flow: Decimal | None
    financing_cash_flow: Decimal | None
    capital_expenditure: Decimal | None
    net_change_in_cash: Decimal | None


@dataclass(frozen=True)
class ProviderFinancialStatement:
    symbol: str
    period_type: str  # "annual" | "quarterly"
    fiscal_year: int
    fiscal_period: str  # "FY" | "Q1".."Q4"
    period_end_date: date
    currency: str
    balance_sheet: ProviderBalanceSheet
    profit_and_loss: ProviderProfitAndLoss
    cash_flow: ProviderCashFlow


class FinancialDataProvider(ABC):
    """Abstract contract every financial statements provider must implement."""

    @abstractmethod
    async def get_annual_statements(self, symbol: str) -> list[ProviderFinancialStatement]:
        """Fetch annual financial statements for a symbol, most recent first."""
        raise NotImplementedError

    @abstractmethod
    async def get_quarterly_statements(self, symbol: str) -> list[ProviderFinancialStatement]:
        """Fetch quarterly financial statements for a symbol, most recent first."""
        raise NotImplementedError

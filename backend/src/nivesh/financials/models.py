"""Financial Statements Engine ORM models.

Slice of the Financial Statements Engine sprint -- ingests, normalizes,
validates, stores, and versions company financial statements. Deterministic
only: every value here is either copied directly from a provider-sourced
statement or computed with plain arithmetic from already-validated figures
(FinancialRatio, QuarterlyResult growth deltas). No AI, no LLM calls.

`FinancialStatement` is the identity + version row for one reporting period
(company, period_type, fiscal_year, fiscal_period) -- the same
"immutable, append-only, a restatement is a new row" convention used by
`ResearchVersion` in research/models.py. There is deliberately no
"is_latest" flag for the same reason research/models.py gives for omitting
`current_version_id`: it would go stale the moment a newer version is
written. "The latest version" is instead `ORDER BY version DESC LIMIT 1`
against the unique `(company_id, period_type, fiscal_year, fiscal_period,
version)` index.

BalanceSheet, ProfitAndLoss, and CashFlowStatement are one-to-one children
of a FinancialStatement holding its line items. QuarterlyResult is a
derived, lightweight quarter-over-quarter trend record (only created for
quarterly statements) -- distinct from ProfitAndLoss, which holds the full
detailed income statement for both annual and quarterly periods.
FinancialRatio holds ratios computed deterministically from a single
statement's balance sheet, P&L, and cash flow figures.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nivesh.core.db import Base

PERIOD_TYPE_ANNUAL = "annual"
PERIOD_TYPE_QUARTERLY = "quarterly"

FISCAL_PERIOD_FULL_YEAR = "FY"
FISCAL_PERIOD_Q1 = "Q1"
FISCAL_PERIOD_Q2 = "Q2"
FISCAL_PERIOD_Q3 = "Q3"
FISCAL_PERIOD_Q4 = "Q4"


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "period_type",
            "fiscal_year",
            "fiscal_period",
            "version",
            name="uq_financial_statements_company_period_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(8), nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    balance_sheet: Mapped["BalanceSheet | None"] = relationship(
        back_populates="statement", uselist=False
    )
    profit_and_loss: Mapped["ProfitAndLoss | None"] = relationship(
        back_populates="statement", uselist=False
    )
    cash_flow: Mapped["CashFlowStatement | None"] = relationship(
        back_populates="statement", uselist=False
    )
    quarterly_result: Mapped["QuarterlyResult | None"] = relationship(
        back_populates="statement", uselist=False
    )
    ratio: Mapped["FinancialRatio | None"] = relationship(back_populates="statement", uselist=False)


class BalanceSheet(Base):
    __tablename__ = "balance_sheets"
    __table_args__ = (
        UniqueConstraint("financial_statement_id", name="uq_balance_sheets_statement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    financial_statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False
    )
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    non_current_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_liabilities: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    non_current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    share_capital: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    reserves_and_surplus: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_debt: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    cash_and_equivalents: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    statement: Mapped["FinancialStatement"] = relationship(back_populates="balance_sheet")


class ProfitAndLoss(Base):
    __tablename__ = "profit_and_loss_statements"
    __table_args__ = (
        UniqueConstraint(
            "financial_statement_id", name="uq_profit_and_loss_statements_statement_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    financial_statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False
    )
    total_revenue: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cost_of_revenue: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    gross_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    operating_expenses: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    interest_expense: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    tax_expense: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_income: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    eps_basic: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    eps_diluted: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    statement: Mapped["FinancialStatement"] = relationship(back_populates="profit_and_loss")


class CashFlowStatement(Base):
    __tablename__ = "cash_flow_statements"
    __table_args__ = (
        UniqueConstraint("financial_statement_id", name="uq_cash_flow_statements_statement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    financial_statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False
    )
    operating_cash_flow: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    investing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    financing_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    capital_expenditure: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_change_in_cash: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    free_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    statement: Mapped["FinancialStatement"] = relationship(back_populates="cash_flow")


class QuarterlyResult(Base):
    """Deterministic quarter-over-quarter trend summary for one quarterly
    FinancialStatement -- revenue/profit headline figures plus QoQ and YoY
    growth computed from sibling quarterly statements already in the
    database. Never created for annual statements."""

    __tablename__ = "quarterly_results"
    __table_args__ = (
        UniqueConstraint("financial_statement_id", name="uq_quarterly_results_statement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    financial_statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False
    )
    revenue: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    net_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    operating_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    net_profit_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    qoq_revenue_growth_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    yoy_revenue_growth_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    qoq_net_profit_growth_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    yoy_net_profit_growth_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    statement: Mapped["FinancialStatement"] = relationship(back_populates="quarterly_result")


class FinancialRatio(Base):
    """Ratios computed deterministically from one statement's own balance
    sheet, P&L, and cash flow figures -- plain division, never estimated or
    inferred. A ratio is None (not zero) when its denominator is missing or
    zero, since "undefined" and "zero" are not the same fact."""

    __tablename__ = "financial_ratios"
    __table_args__ = (
        UniqueConstraint("financial_statement_id", name="uq_financial_ratios_statement_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    financial_statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False
    )
    current_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    net_profit_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    operating_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    return_on_equity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    return_on_assets: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    asset_turnover: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    interest_coverage_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    statement: Mapped["FinancialStatement"] = relationship(back_populates="ratio")

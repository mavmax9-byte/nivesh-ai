"""Financial statements engine: statements, balance sheets, P&L, cash flow, results, ratios

Revision ID: 0003_financial_statements
Revises: 0002_research_dossier
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_financial_statements"
down_revision: str | None = "0002_research_dossier"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=8), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_financial_statements_company_id", "financial_statements", ["company_id"])
    op.create_unique_constraint(
        "uq_financial_statements_company_period_version",
        "financial_statements",
        ["company_id", "period_type", "fiscal_year", "fiscal_period", "version"],
    )

    op.create_table(
        "balance_sheets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "financial_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_statements.id"),
            nullable=False,
        ),
        sa.Column("total_assets", sa.Numeric(20, 2), nullable=False),
        sa.Column("current_assets", sa.Numeric(20, 2), nullable=True),
        sa.Column("non_current_assets", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_liabilities", sa.Numeric(20, 2), nullable=False),
        sa.Column("current_liabilities", sa.Numeric(20, 2), nullable=True),
        sa.Column("non_current_liabilities", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_equity", sa.Numeric(20, 2), nullable=False),
        sa.Column("share_capital", sa.Numeric(20, 2), nullable=True),
        sa.Column("reserves_and_surplus", sa.Numeric(20, 2), nullable=True),
        sa.Column("total_debt", sa.Numeric(20, 2), nullable=True),
        sa.Column("cash_and_equivalents", sa.Numeric(20, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_balance_sheets_statement_id", "balance_sheets", ["financial_statement_id"]
    )

    op.create_table(
        "profit_and_loss_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "financial_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_statements.id"),
            nullable=False,
        ),
        sa.Column("total_revenue", sa.Numeric(20, 2), nullable=False),
        sa.Column("cost_of_revenue", sa.Numeric(20, 2), nullable=True),
        sa.Column("gross_profit", sa.Numeric(20, 2), nullable=True),
        sa.Column("operating_expenses", sa.Numeric(20, 2), nullable=True),
        sa.Column("operating_income", sa.Numeric(20, 2), nullable=True),
        sa.Column("interest_expense", sa.Numeric(20, 2), nullable=True),
        sa.Column("tax_expense", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_income", sa.Numeric(20, 2), nullable=False),
        sa.Column("eps_basic", sa.Numeric(12, 4), nullable=True),
        sa.Column("eps_diluted", sa.Numeric(12, 4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_profit_and_loss_statements_statement_id",
        "profit_and_loss_statements",
        ["financial_statement_id"],
    )

    op.create_table(
        "cash_flow_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "financial_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_statements.id"),
            nullable=False,
        ),
        sa.Column("operating_cash_flow", sa.Numeric(20, 2), nullable=False),
        sa.Column("investing_cash_flow", sa.Numeric(20, 2), nullable=True),
        sa.Column("financing_cash_flow", sa.Numeric(20, 2), nullable=True),
        sa.Column("capital_expenditure", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_change_in_cash", sa.Numeric(20, 2), nullable=True),
        sa.Column("free_cash_flow", sa.Numeric(20, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_cash_flow_statements_statement_id", "cash_flow_statements", ["financial_statement_id"]
    )

    op.create_table(
        "quarterly_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "financial_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_statements.id"),
            nullable=False,
        ),
        sa.Column("revenue", sa.Numeric(20, 2), nullable=False),
        sa.Column("net_profit", sa.Numeric(20, 2), nullable=False),
        sa.Column("eps", sa.Numeric(12, 4), nullable=True),
        sa.Column("operating_margin", sa.Numeric(10, 4), nullable=True),
        sa.Column("net_profit_margin", sa.Numeric(10, 4), nullable=True),
        sa.Column("qoq_revenue_growth_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("yoy_revenue_growth_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("qoq_net_profit_growth_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("yoy_net_profit_growth_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_quarterly_results_statement_id", "quarterly_results", ["financial_statement_id"]
    )

    op.create_table(
        "financial_ratios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "financial_statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_statements.id"),
            nullable=False,
        ),
        sa.Column("current_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(10, 4), nullable=True),
        sa.Column("net_profit_margin", sa.Numeric(10, 4), nullable=True),
        sa.Column("operating_margin", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_on_equity", sa.Numeric(10, 4), nullable=True),
        sa.Column("return_on_assets", sa.Numeric(10, 4), nullable=True),
        sa.Column("asset_turnover", sa.Numeric(10, 4), nullable=True),
        sa.Column("interest_coverage_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_financial_ratios_statement_id", "financial_ratios", ["financial_statement_id"]
    )


def downgrade() -> None:
    op.drop_table("financial_ratios")
    op.drop_table("quarterly_results")
    op.drop_table("cash_flow_statements")
    op.drop_table("profit_and_loss_statements")
    op.drop_table("balance_sheets")
    op.drop_table("financial_statements")

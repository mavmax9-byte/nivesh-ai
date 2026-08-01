"""portfolio_planner: AI-generated illustrative portfolio allocations

Revision ID: 0010_portfolio_planner
Revises: 0009_agent_findings
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_portfolio_planner"
down_revision: str | None = "0009_agent_findings"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capital", sa.Numeric(18, 2), nullable=False),
        sa.Column("risk_profile", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.String(length=16), nullable=False),
        sa.Column("sector_exclusions", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("caveats", postgresql.JSONB(), nullable=False),
        sa.Column("unallocated_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("evidence_sufficiency", sa.String(length=16), nullable=True),
        sa.Column("universe_size", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "planned_portfolio_holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("planned_portfolios.id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("allocated_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("allocated_weight", sa.Float(), nullable=False),
        sa.Column("rank_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("evidence_sufficiency", sa.String(length=16), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("weight_rationale", sa.Text(), nullable=False),
        sa.Column("top_citation_title", sa.String(length=512), nullable=True),
        sa.Column("top_citation_source_type", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_planned_portfolio_holdings_portfolio_id",
        "planned_portfolio_holdings",
        ["portfolio_id"],
    )


def downgrade() -> None:
    op.drop_table("planned_portfolio_holdings")
    op.drop_table("planned_portfolios")

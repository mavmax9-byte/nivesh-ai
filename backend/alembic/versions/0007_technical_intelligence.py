"""Technical intelligence engine: technical indicators

Revision ID: 0007_technical_intelligence
Revises: 0006_news_intelligence
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_technical_intelligence"
down_revision: str | None = "0006_news_intelligence"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "technical_indicators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("indicator_name", sa.String(length=32), nullable=False),
        sa.Column("indicator_parameters", postgresql.JSONB(), nullable=False),
        sa.Column("indicator_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("calculation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_technical_indicators_company_id", "technical_indicators", ["company_id"])
    op.create_index(
        "ix_technical_indicators_trading_date", "technical_indicators", ["trading_date"]
    )
    op.create_unique_constraint(
        "uq_technical_indicators_company_date_name",
        "technical_indicators",
        ["company_id", "trading_date", "indicator_name"],
    )


def downgrade() -> None:
    op.drop_table("technical_indicators")

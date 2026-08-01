"""market_universe: tracked index membership, ingestion status, screening

Revision ID: 0011_market_universe
Revises: 0010_portfolio_planner
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_market_universe"
down_revision: str | None = "0010_portfolio_planner"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "universe_constituents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("index_name", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
        sa.Column("ingestion_status", sa.String(length=16), nullable=False),
        sa.Column("ingestion_error", sa.Text(), nullable=True),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("screening_score", sa.Float(), nullable=True),
        sa.Column("is_screened_in", sa.Boolean(), nullable=False),
        sa.Column("screened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("index_name", "symbol", name="uq_universe_constituents_index_symbol"),
    )
    op.create_index(
        "ix_universe_constituents_index_status",
        "universe_constituents",
        ["index_name", "ingestion_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_universe_constituents_index_status", table_name="universe_constituents")
    op.drop_table("universe_constituents")

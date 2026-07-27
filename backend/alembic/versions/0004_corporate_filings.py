"""Corporate filings metadata engine: categories, sources, filings, filing versions

Revision ID: 0004_corporate_filings
Revises: 0003_financial_statements
Create Date: 2026-07-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_corporate_filings"
down_revision: str | None = "0003_financial_statements"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "filing_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint("uq_filing_categories_code", "filing_categories", ["code"])

    op.create_table(
        "filing_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint("uq_filing_sources_code", "filing_sources", ["code"])

    op.create_table(
        "corporate_filings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("filing_type", sa.String(length=32), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("filing_categories.id"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("filing_sources.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("reporting_period", sa.String(length=32), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("document_size", sa.Integer(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "ingestion_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_corporate_filings_company_id", "corporate_filings", ["company_id"])
    op.create_unique_constraint(
        "uq_corporate_filings_company_type_period",
        "corporate_filings",
        ["company_id", "filing_type", "reporting_period"],
    )
    op.create_unique_constraint("uq_corporate_filings_checksum", "corporate_filings", ["checksum"])

    op.create_table(
        "filing_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "filing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("corporate_filings.id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("document_size", sa.Integer(), nullable=True),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_filing_versions_filing_version", "filing_versions", ["filing_id", "version_number"]
    )
    op.create_index("ix_filing_versions_company_id", "filing_versions", ["company_id"])


def downgrade() -> None:
    op.drop_table("filing_versions")
    op.drop_table("corporate_filings")
    op.drop_table("filing_sources")
    op.drop_table("filing_categories")

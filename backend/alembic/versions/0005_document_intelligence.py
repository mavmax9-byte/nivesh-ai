"""Document intelligence engine: document extractions, document sections

Revision ID: 0005_document_intelligence
Revises: 0004_corporate_filings
Create Date: 2026-07-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_document_intelligence"
down_revision: str | None = "0004_corporate_filings"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "filing_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("filing_versions.id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("extraction_status", sa.String(length=16), nullable=False),
        sa.Column("extractor_name", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=32), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_document_extractions_filing_version_id", "document_extractions", ["filing_version_id"]
    )
    op.create_index("ix_document_extractions_company_id", "document_extractions", ["company_id"])
    op.create_unique_constraint(
        "uq_document_extractions_filing_version_id",
        "document_extractions",
        ["filing_version_id"],
    )

    op.create_table(
        "document_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_extraction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_extractions.id"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=512), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_document_sections_document_extraction_id",
        "document_sections",
        ["document_extraction_id"],
    )
    op.create_unique_constraint(
        "uq_document_sections_extraction_sequence",
        "document_sections",
        ["document_extraction_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_table("document_sections")
    op.drop_table("document_extractions")

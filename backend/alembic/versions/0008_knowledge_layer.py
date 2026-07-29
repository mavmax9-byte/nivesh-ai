"""Knowledge layer: embeddings for semantic retrieval

Revision ID: 0008_knowledge_layer
Revises: 0007_technical_intelligence
Create Date: 2026-07-29

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_knowledge_layer"
down_revision: str | None = "0007_technical_intelligence"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Must match knowledge_layer/models.py's EMBEDDING_DIMENSIONS constant.
_EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_checksum", sa.String(length=128), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(_EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.String(length=64), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_knowledge_embeddings_company_id", "knowledge_embeddings", ["company_id"])
    op.create_unique_constraint(
        "uq_knowledge_embeddings_source_type_id",
        "knowledge_embeddings",
        ["source_type", "source_id"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")

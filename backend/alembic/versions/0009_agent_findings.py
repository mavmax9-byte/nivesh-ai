"""ai_agents: persisted specialist-agent findings

Revision ID: 0009_agent_findings
Revises: 0008_knowledge_layer
Create Date: 2026-07-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_agent_findings"
down_revision: str | None = "0008_knowledge_layer"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("agent_code", sa.String(length=32), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model_used", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("evidence_sufficiency", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_agent_findings_company_id", "agent_findings", ["company_id"])
    op.create_unique_constraint(
        "uq_agent_findings_company_agent", "agent_findings", ["company_id", "agent_code"]
    )


def downgrade() -> None:
    op.drop_table("agent_findings")

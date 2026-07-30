"""ai_agents ORM models.

`AgentFinding` is this module's first-ever database table -- `ai_agents`
had zero DB presence before v0.9. Confirmed during v0.9 planning
(FUNDAMENTAL_ANALYST_DESIGN.md §14) as a deliberate divergence from
`retrieval_engine`'s stateless choice (PROJECT_CONTEXT.md §13 point 1b):
a finding is a durable analysis result worth looking back on, unlike a
retrieval call, which is a transient lookup over evidence every other
module already owns.

Upsert-recomputed, not versioned -- the same "pattern 4" shape
`TechnicalIndicator` already established (PROJECT_CONTEXT.md §4): a
finding is not an immutable fact about something that happened, it is the
output of a reasoning pass over currently-available evidence, and a
re-run against fresher evidence supersedes rather than amends the prior
one. One current row per `(company_id, agent_code)` -- `ON CONFLICT DO
UPDATE`, never a version history table.

`result_json` holds the full structured payload a specialist agent
produced (e.g. `FundamentalAnalysisResult` for
`agent_code="fundamental_analyst"`), so each future specialist agent can
persist its own richer shape without a schema change here -- the same
"extend the catalog, not the schema" spirit `research/models.py`'s
`SourceType` catalog already follows. `confidence_score` and
`evidence_sufficiency` are denormalized out of `result_json` onto their
own columns purely so they're queryable/filterable without parsing JSON.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nivesh.core.db import Base

AGENT_CODE_FUNDAMENTAL_ANALYST = "fundamental_analyst"

VALID_AGENT_CODES = {AGENT_CODE_FUNDAMENTAL_ANALYST}


class AgentFinding(Base):
    __tablename__ = "agent_findings"
    __table_args__ = (
        UniqueConstraint("company_id", "agent_code", name="uq_agent_findings_company_agent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    agent_code: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_sufficiency: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

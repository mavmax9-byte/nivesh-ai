"""Market Universe ORM models.

Tracks which companies belong to a tracked index universe (today, just
`NIFTY50`), their ingestion progress through the existing per-domain sync
pipelines, and a deterministic screening score computed from that
ingested data. This table owns none of the ingested data itself -- it
only tracks membership/status/score, the same way `agent_findings`
tracks a *result* without owning the evidence it was computed from.

`company_id` is nullable and populated only after first ingestion
succeeds (mirroring `sync_company_market_data`'s own upsert-by-symbol
behavior, which is what actually creates/updates the `Company` row) --
a constituent can legitimately exist in "pending, never ingested" state
with no `Company` row yet. Per PROJECT_CONTEXT.md's cross-module rule,
this is a plain `ForeignKey` column, never a SQLAlchemy `relationship()`
reaching into `companies`.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nivesh.core.db import Base

STATUS_PENDING = "pending"
STATUS_INGESTING = "ingesting"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
VALID_INGESTION_STATUSES = {STATUS_PENDING, STATUS_INGESTING, STATUS_READY, STATUS_FAILED}


class UniverseConstituent(Base):
    __tablename__ = "universe_constituents"
    __table_args__ = (
        UniqueConstraint("index_name", "symbol", name="uq_universe_constituents_index_symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    index_name: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    ingestion_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING
    )
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    screening_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_screened_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    screened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

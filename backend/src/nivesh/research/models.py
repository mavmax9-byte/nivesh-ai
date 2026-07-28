"""Research Dossier ORM models.

Implements docs/v2 01-Research-Pipeline.md and 02-Company-Research-Dossier.md
and docs/db 12-Research-Dossier.md at the deterministic-evidence stage only
-- no AI/reasoning-plane tables (Findings Store, Investment Committee,
Evidence Graph claims) are part of this sprint.

`CompanyResearchDossier` is the one mutable row per company (the "pointer"),
mirroring docs/db 12 section 12.8's DossierSectionPointer precedent: it is
updated in place to track the current version number and a watermark of the
market data last incorporated. Every other table here is append-only and
immutable once written -- a version, its snapshot, its evidence sources, and
timeline events are never edited or deleted, only ever added.

There is deliberately no `current_version_id` foreign key on the dossier
pointing back into `research_versions` -- that would create a circular
table dependency between the two tables. "The latest version" is instead a
cheap, index-backed query (`ORDER BY version_number DESC LIMIT 1` on the
unique `(dossier_id, version_number)` index), and `current_version_number`
is kept as a plain denormalized counter (not a foreign key) purely so the
pipeline can compute the next version number without a query.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nivesh.core.db import Base

# Valid values for ResearchVersion.triggered_by (enforced at the Pydantic
# schema layer, per the plain-string-column convention already used for
# CorporateAction.action_type in market_data/models.py).
TRIGGERED_BY_MARKET_DATA_SYNC = "market_data_sync"
TRIGGERED_BY_MANUAL = "manual"

# Valid values for ResearchTimeline.event_type.
EVENT_TYPE_VERSION_CREATED = "version_created"

# Valid values for ResearchSource.source_type. "market_data",
# "corporate_action", "financial_data", "corporate_filing", and
# "document_extraction" are populated by their respective sprints'
# pipelines -- "news" and "technical_indicator" exist now so later sprints
# (which add those data sources) extend this catalog, not the schema.
SOURCE_TYPE_MARKET_DATA = "market_data"
SOURCE_TYPE_FINANCIAL_DATA = "financial_data"
SOURCE_TYPE_CORPORATE_ACTION = "corporate_action"
SOURCE_TYPE_CORPORATE_FILING = "corporate_filing"
SOURCE_TYPE_DOCUMENT_EXTRACTION = "document_extraction"
SOURCE_TYPE_NEWS = "news"
SOURCE_TYPE_TECHNICAL_INDICATOR = "technical_indicator"


class CompanyResearchDossier(Base):
    __tablename__ = "company_research_dossiers"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_research_dossiers_company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_market_data_watermark: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["ResearchVersion"]] = relationship(
        back_populates="dossier", order_by="ResearchVersion.version_number.desc()"
    )


class ResearchVersion(Base):
    """One immutable version of a company's research dossier.

    Never updated or deleted once created -- a new version is always a new
    row, so every prior version remains exactly as it was when published.
    """

    __tablename__ = "research_versions"
    __table_args__ = (
        UniqueConstraint(
            "dossier_id", "version_number", name="uq_research_versions_dossier_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_research_dossiers.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dossier: Mapped["CompanyResearchDossier"] = relationship(back_populates="versions")
    snapshot: Mapped["ResearchSnapshot | None"] = relationship(
        back_populates="version", uselist=False
    )


class ResearchSnapshot(Base):
    """The structured, deterministic content of one research version.

    Purely factual aggregation of already-validated market data -- no
    interpretation, no AI-generated text. One row per ResearchVersion.
    """

    __tablename__ = "research_snapshots"
    __table_args__ = (UniqueConstraint("version_id", name="uq_research_snapshots_version_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_versions.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latest_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    latest_trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_bar_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_history_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_history_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    corporate_action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_corporate_action_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version: Mapped["ResearchVersion"] = relationship(back_populates="snapshot")


class ResearchTimeline(Base):
    """Append-only chronological activity feed for a dossier."""

    __tablename__ = "research_timeline"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_research_dossiers.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_versions.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchSource(Base):
    """A structured, typed pointer from a research version to underlying
    evidence -- market data, corporate actions, and (in later sprints)
    financial statements, news, and technical indicators.

    High-volume, continuous evidence (market_data, technical_indicator) is
    referenced as an aggregate date range with a record count; discrete,
    low-volume evidence (corporate_action, news, financial_data) is
    referenced one row per underlying record via `reference_id`. This is
    evidence bookkeeping only -- no confidence score, no claim, no AI
    weighing of the evidence (that is Evidence Graph / AI Layer territory,
    out of scope here).
    """

    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_research_dossiers.id"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_versions.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_table: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    range_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    range_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

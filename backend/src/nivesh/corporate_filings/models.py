"""Corporate Filings Metadata Engine ORM models.

Maintains a structured catalog of corporate filings (regulatory
disclosures, results, announcements) for Indian listed companies --
metadata only. This sprint never downloads or parses the underlying
documents; `source_url` is a pointer to where the document lives, not
content this platform stores.

`CorporateFiling` is the current, mutable state of one filing identity
(company, filing_type, reporting_period) -- unlike ResearchVersion or
FinancialStatement, where a restatement is a brand new row, a filing that
gets corrected/reissued upstream (a new checksum for the same identity) is
represented by updating this row in place and incrementing
`version_number`. `FilingVersion` is the append-only, immutable audit
trail of every state this row has ever held, the same "never edited or
deleted, only ever added" invariant used by ResearchVersion in
research/models.py, just without a separate pointer/version table split --
the current state IS the row, `version_number` says how many times it has
changed, and FilingVersion is the paper trail.

`FilingCategory` and `FilingSource` are small reference/lookup tables,
following the exact `Exchange` precedent in companies/models.py: a
handful of rows, looked up and created on demand via
`get_or_create_by_code`, never created ad hoc by application code.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nivesh.core.db import Base

# Valid values for CorporateFiling.filing_type.
FILING_TYPE_ANNUAL_REPORT = "annual_report"
FILING_TYPE_QUARTERLY_RESULTS = "quarterly_results"
FILING_TYPE_BOARD_MEETING = "board_meeting"
FILING_TYPE_SHAREHOLDING_PATTERN = "shareholding_pattern"
FILING_TYPE_CORPORATE_ACTION = "corporate_action"
FILING_TYPE_INVESTOR_PRESENTATION = "investor_presentation"
FILING_TYPE_CREDIT_RATING = "credit_rating"
FILING_TYPE_REGULATORY_DISCLOSURE = "regulatory_disclosure"
FILING_TYPE_OTHER = "other"

VALID_FILING_TYPES = {
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_QUARTERLY_RESULTS,
    FILING_TYPE_BOARD_MEETING,
    FILING_TYPE_SHAREHOLDING_PATTERN,
    FILING_TYPE_CORPORATE_ACTION,
    FILING_TYPE_INVESTOR_PRESENTATION,
    FILING_TYPE_CREDIT_RATING,
    FILING_TYPE_REGULATORY_DISCLOSURE,
    FILING_TYPE_OTHER,
}

# filing_type values surfaced by the GET /filings/{symbol}/annual and
# .../quarterly endpoints.
ANNUAL_FILING_TYPES = {FILING_TYPE_ANNUAL_REPORT}
QUARTERLY_FILING_TYPES = {FILING_TYPE_QUARTERLY_RESULTS}

# FilingCategory.code values -- the broader groupings filing_type rolls
# up into, exposed via GET /filings/{symbol}/category/{category}.
CATEGORY_FINANCIAL_RESULTS = "financial_results"
CATEGORY_GOVERNANCE = "governance"
CATEGORY_CORPORATE_ACTIONS = "corporate_actions"
CATEGORY_INVESTOR_COMMUNICATION = "investor_communication"
CATEGORY_DISCLOSURES = "disclosures"


class FilingCategory(Base):
    __tablename__ = "filing_categories"
    __table_args__ = (UniqueConstraint("code", name="uq_filing_categories_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FilingSource(Base):
    __tablename__ = "filing_sources"
    __table_args__ = (UniqueConstraint("code", name="uq_filing_sources_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorporateFiling(Base):
    __tablename__ = "corporate_filings"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "filing_type",
            "reporting_period",
            name="uq_corporate_filings_company_type_period",
        ),
        UniqueConstraint("checksum", name="uq_corporate_filings_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    # Plain exchange code (e.g. "NSE"/"BSE"), not a foreign key to
    # companies.exchange_id -- the same "no Security/Listing separation"
    # simplification companies/models.py documents, applied here because a
    # dual-listed company's filings are announced independently per
    # exchange and may not match the company's primary listing.
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("filing_categories.id"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_sources.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    reporting_period: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    document_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ingestion_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["FilingCategory"] = relationship()
    source: Mapped["FilingSource"] = relationship()
    versions: Mapped[list["FilingVersion"]] = relationship(
        back_populates="filing", order_by="FilingVersion.version_number.desc()"
    )


class FilingVersion(Base):
    """One immutable snapshot of a CorporateFiling's state -- written every
    time that row's content changes, never edited or deleted afterward."""

    __tablename__ = "filing_versions"
    __table_args__ = (
        UniqueConstraint("filing_id", "version_number", name="uq_filing_versions_filing_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("corporate_filings.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    document_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    filing: Mapped["CorporateFiling"] = relationship(back_populates="versions")

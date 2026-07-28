"""Document Intelligence Engine ORM models.

Converts corporate filing documents (Corporate Filings Metadata Engine, v0.3)
into structured, searchable knowledge -- text extraction only. No AI, no
embeddings, no vector storage: every value here is either copied verbatim
from a mechanically parsed document or computed by plain counting (page and
section counts). The Corporate Filings module remains the only place filing
*discovery* happens; this module never re-discovers filings, it only
processes ones that already exist there.

`FilingVersion` (corporate_filings/models.py) is the document identity this
module extracts against -- a restated/reissued filing gets a new
FilingVersion upstream, and that new version gets its own independent
extraction. `DocumentExtraction` therefore has at most one row per
`filing_version_id` (see `uq_document_extractions_filing_version_id`): unlike
FinancialStatement or CorporateFiling, there is no versioning concept of its
own to model here -- the identity to extract against is already versioned by
the upstream module.

`DocumentSection` is the structured decomposition of one extraction's text
into headings/pages, giving clean section storage without turning
`extracted_text` itself into anything but a flat canonical string. Both
tables are populated once, on successful extraction, and are never edited in
place afterward -- a re-extraction is blocked as a duplicate (see
validation.py), not performed.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nivesh.core.db import Base

# Valid values for DocumentExtraction.extraction_status. Only "completed" is
# ever persisted by this sprint's service (validation failures and provider
# errors raise before any row is written, matching financials/corporate_filings'
# convention) -- "failed" is reserved for a later sprint that may want to
# record a terminal, non-retryable extraction failure as its own row.
EXTRACTION_STATUS_COMPLETED = "completed"
EXTRACTION_STATUS_FAILED = "failed"

VALID_EXTRACTION_STATUSES = {EXTRACTION_STATUS_COMPLETED, EXTRACTION_STATUS_FAILED}


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    __table_args__ = (
        UniqueConstraint("filing_version_id", name="uq_document_extractions_filing_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filing_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("filing_versions.id"), nullable=False, index=True
    )
    # Denormalized from the filing version's own company_id, the same
    # convenience-for-querying precedent FilingVersion itself documents in
    # corporate_filings/models.py -- lets list_by_company query this table
    # directly without joining back through filing_versions/corporate_filings.
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    extraction_status: Mapped[str] = mapped_column(String(16), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["DocumentSection"]] = relationship(
        back_populates="extraction", order_by="DocumentSection.sequence"
    )


class DocumentSection(Base):
    """One heading-delimited slice of an extraction's text, in document order.

    Sequence is 0-based and strictly increasing within one extraction;
    `page_number` is the page the section's heading was found on, per the
    "preserve page numbers, headings, section hierarchy" requirement.
    """

    __tablename__ = "document_sections"
    __table_args__ = (
        UniqueConstraint(
            "document_extraction_id",
            "sequence",
            name="uq_document_sections_extraction_sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_extraction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_extractions.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(512), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    extraction: Mapped["DocumentExtraction"] = relationship(back_populates="sections")

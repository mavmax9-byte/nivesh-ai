"""Knowledge Layer ORM models.

Stores one embedding vector per unit of *textual* knowledge already
persisted elsewhere in the platform -- a company profile, a corporate
filing's own metadata, a Document Intelligence section, a news article, or
a Research Dossier version's change summary. This module never discovers
or ingests knowledge itself; it only reads text other modules have already
validated and persisted, embeds it, and stores the vector plus enough
metadata to trace every result back to its origin row. No AI reasoning, no
summarization, no report generation lives here -- see service.py's module
docstring for the full boundary.

`KnowledgeEmbedding` is this codebase's second entity-attribute-value-style
table (after `technical_intelligence.TechnicalIndicator`) in the sense that
one row represents one derived value keyed off an origin row elsewhere, but
its persistence pattern is deliberately different: TechnicalIndicator
upserts unconditionally on every run because indicator math is free CPU: an
OpenAI embedding call costs real money and a network round trip, so
`content_checksum` lets the service layer skip calling the provider at all
when a source row's text hasn't changed since the last run (see
service.py). This is a fifth persistence pattern for this codebase --
"upsert-recomputed, gated by a checksum guard so recomputation only happens
when the underlying content actually changed" -- distinct from the four
already documented in PROJECT_CONTEXT.md's Database Schema section.

Identity is `(source_type, source_id)`, unique -- one embedding per source
unit, no chunking in this version (a source row's text is truncated to fit
one embedding call rather than split into multiple chunks; see
normalization.py). `source_id` points at the origin row's own primary key
in whichever table `source_table` names; for `company_profile`, the
"origin row" is the company itself, so `source_id` is simply
`company_id` again -- there is no separate child row to point at.

No vector index (ivfflat/hnsw) is created in this version. pgvector's
distance operators work correctly without one (an exact, not approximate,
sequential scan); queries are always scoped to one company
(`WHERE company_id = ...`), which bounds the scan to that company's own
knowledge units rather than the whole table. Adding an approximate index
is a reasonable future step once real data volumes are known, not a gap in
this version's correctness.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nivesh.core.db import Base

# text-embedding-3-small's native output size (see config.py's
# EMBEDDING_DIMENSIONS, the same value, kept independent here since a
# column type is fixed at migration time and must never silently follow a
# runtime setting -- changing embedding models/dimensions is a migration,
# not a config change).
EMBEDDING_DIMENSIONS = 1536

# Valid values for KnowledgeEmbedding.source_type -- what kind of textual
# knowledge a row embeds. Distinct from research.models.SOURCE_TYPE_* (the
# Research Dossier's own, coarser evidence-category catalog): these
# describe *what was embedded*, not how it's referenced as dossier
# evidence (a knowledge_embedding generation run is linked to the dossier
# as a single aggregate SOURCE_TYPE_KNOWLEDGE_EMBEDDING source -- see
# service.py).
SOURCE_TYPE_COMPANY_PROFILE = "company_profile"
SOURCE_TYPE_CORPORATE_FILING = "corporate_filing"
SOURCE_TYPE_DOCUMENT_SECTION = "document_section"
SOURCE_TYPE_NEWS_ARTICLE = "news_article"
SOURCE_TYPE_RESEARCH_SUMMARY = "research_summary"

VALID_KNOWLEDGE_SOURCE_TYPES = {
    SOURCE_TYPE_COMPANY_PROFILE,
    SOURCE_TYPE_CORPORATE_FILING,
    SOURCE_TYPE_DOCUMENT_SECTION,
    SOURCE_TYPE_NEWS_ARTICLE,
    SOURCE_TYPE_RESEARCH_SUMMARY,
}

# The origin table each source_type's source_id points into.
SOURCE_TABLE_BY_TYPE = {
    SOURCE_TYPE_COMPANY_PROFILE: "companies",
    SOURCE_TYPE_CORPORATE_FILING: "corporate_filings",
    SOURCE_TYPE_DOCUMENT_SECTION: "document_sections",
    SOURCE_TYPE_NEWS_ARTICLE: "news_articles",
    SOURCE_TYPE_RESEARCH_SUMMARY: "research_versions",
}


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_knowledge_embeddings_source_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

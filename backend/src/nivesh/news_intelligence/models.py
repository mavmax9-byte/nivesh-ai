"""News Intelligence Engine ORM models.

Maintains a per-company catalog of news articles ingested from external
news providers -- no AI summarization, no sentiment analysis, no semantic
matching. Every field is either copied directly from a provider response or
assigned deterministically (checksum, category).

`NewsArticle` has no version-history table, unlike CorporateFiling/
FilingVersion -- a news article is inherently immutable once published (a
provider republishing a "corrected" story is, for this platform's purposes,
a different article, not a new version of an old one), so it follows the
same "no versioning needed" precedent DocumentExtraction established in
document_intelligence/models.py: the row itself is the whole, permanent
record, and uniqueness is enforced by a `checksum` constraint rather than a
version table.

Deduplication is deliberately scoped **per-provider only** in this version
(a decision made explicitly during v0.5 planning): `checksum` is derived
from (company_id, provider, normalized url), so re-syncing the same
provider is idempotent, but two different providers reporting the same
real-world story under different URLs are stored as two separate articles
rather than merged. True cross-provider identity resolution was considered
and explicitly deferred -- see normalization.py's module docstring -- until
a second real provider exists to design and test that logic against actual
data rather than speculatively.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nivesh.core.db import Base

# Valid values for NewsArticle.category -- a small, fixed set assigned
# deterministically from the article title (see normalization.py), never
# inferred by a model. "general" is the default when no keyword matches.
CATEGORY_GENERAL = "general"
CATEGORY_EARNINGS = "earnings"
CATEGORY_CORPORATE_ACTION = "corporate_action"
CATEGORY_REGULATORY = "regulatory"
CATEGORY_MARKETS = "markets"

VALID_NEWS_CATEGORIES = {
    CATEGORY_GENERAL,
    CATEGORY_EARNINGS,
    CATEGORY_CORPORATE_ACTION,
    CATEGORY_REGULATORY,
    CATEGORY_MARKETS,
}


class NewsArticle(Base):
    """One immutable news article for one company.

    `source` is the originating publication/outlet the provider attributes
    the story to (e.g. "Reuters", "Bloomberg") -- purely descriptive
    metadata about the article. `provider` is this platform's own internal
    data-provider code (e.g. "yfinance-dev") that fetched it -- the same
    role FilingSource.code plays in corporate_filings, kept here as a plain
    column rather than a reference table since, unlike filing sources, a
    news provider is exclusively selected by providers/factory.py and never
    looked up or displayed independently of an article.
    """

    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("checksum", name="uq_news_articles_checksum"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default=CATEGORY_GENERAL)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    ingestion_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

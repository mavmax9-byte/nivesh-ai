"""News Intelligence Engine data-access layer.

`NewsArticleRepository` follows the simpler, non-aggregate-root convention
used by companies/repository.py: unlike CorporateFiling (parent row + a
FilingVersion history sibling that must land together) or DocumentExtraction
(extraction + sections that must land together), a NewsArticle is a single,
flat, immutable row with no child rows requiring atomic co-commit. Writes
still use `flush()` rather than committing per row, purely so a whole
sync's batch of new articles is committed once by the service (see
NewsIntelligenceService.sync_company_news) rather than one round trip per
article -- if any row in the batch fails a constraint, the whole batch's
flush fails before any of it commits.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.news_intelligence.models import NewsArticle


class NewsArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -----------------------------------------------------------

    async def get_by_checksum(self, checksum: str) -> NewsArticle | None:
        result = await self._session.execute(
            select(NewsArticle).where(NewsArticle.checksum == checksum)
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[NewsArticle]:
        result = await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.company_id == company_id)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_category(
        self, company_id: uuid.UUID, category: str, limit: int = 50
    ) -> list[NewsArticle]:
        result = await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.company_id == company_id, NewsArticle.category == category)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # -- writes (flush only -- see module docstring) ----------------------

    async def create_article(self, data: dict) -> NewsArticle:
        article = NewsArticle(**data)
        self._session.add(article)
        await self._session.flush()
        return article

    async def commit(self) -> None:
        """Commits whatever is pending on this repository's session -- the
        newly flushed article batch, and later, Research Dossier evidence
        rows written through ResearchDossierRepository's flush-only methods
        on this same shared session (see
        NewsIntelligenceService._link_to_research_dossier)."""
        await self._session.commit()

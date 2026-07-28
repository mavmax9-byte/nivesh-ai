"""News Intelligence Engine service.

Orchestrates provider fetches, validation, normalization, and persistence,
then links the results into the existing Research Dossier as evidence.
`SOURCE_TYPE_NEWS` was already reserved (unused) in research/models.py's
SourceType catalog since Sprint 3 specifically for this -- this sprint is
the first to actually populate it, requiring zero changes to
research/models.py or research/schemas.py. No AI, no LLM calls, no
sentiment analysis, no embeddings: every value here is either copied
directly from a provider-sourced article or assigned deterministically
(category via a fixed keyword lookup in normalization.py, checksum via a
SHA-256 fingerprint).
"""

import logging
import uuid
from dataclasses import dataclass

from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.news_intelligence.models import NewsArticle
from nivesh.news_intelligence.normalization import normalize_article
from nivesh.news_intelligence.providers.base import NewsProvider, ProviderNewsArticle
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.news_intelligence.validation import (
    validate_category,
    validate_checksum_format,
    validate_published_at,
    validate_required_fields,
    validate_url,
)
from nivesh.research.models import SOURCE_TYPE_NEWS
from nivesh.research.repository import ResearchDossierRepository

logger = logging.getLogger(__name__)

PROVIDER_SOURCE_CODE = "yfinance-dev"
PROVIDER_SOURCE_TABLE = "news_articles"
EVENT_TYPE_NEWS_SYNCED = "news_synced"


@dataclass(frozen=True)
class NewsSyncResult:
    company_id: uuid.UUID
    symbol: str
    articles_synced: int
    articles_unchanged: int


class NewsIntelligenceService:
    def __init__(
        self,
        provider: NewsProvider,
        company_repository: CompanyRepository,
        article_repository: NewsArticleRepository,
        dossier_repository: ResearchDossierRepository,
    ) -> None:
        self._provider = provider
        self._companies = company_repository
        self._articles = article_repository
        self._dossiers = dossier_repository

    async def sync_company_news(self, symbol: str) -> NewsSyncResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        provider_articles = await self._provider.get_news(symbol)

        synced: list[NewsArticle] = []
        unchanged = 0
        seen_checksums: set[str] = set()

        for provider_article in provider_articles:
            article, was_new = await self._persist_article(
                company.id, provider_article, seen_checksums
            )
            if was_new:
                synced.append(article)  # type: ignore[arg-type]
            else:
                unchanged += 1

        if synced:
            await self._articles.commit()

        await self._link_to_research_dossier(company.id, company.symbol, synced)

        return NewsSyncResult(
            company_id=company.id,
            symbol=company.symbol,
            articles_synced=len(synced),
            articles_unchanged=unchanged,
        )

    async def get_news(self, symbol: str, limit: int = 50, offset: int = 0) -> list[NewsArticle]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._articles.list_by_company(company.id, limit=limit, offset=offset)

    async def get_news_by_category(
        self, symbol: str, category: str, limit: int = 50
    ) -> list[NewsArticle]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._articles.list_by_category(company.id, category, limit=limit)

    # -- internals -----------------------------------------------------

    async def _persist_article(
        self,
        company_id: uuid.UUID,
        provider_article: ProviderNewsArticle,
        seen_checksums: set[str],
    ) -> tuple[NewsArticle | None, bool]:
        validate_url(provider_article.url)
        validate_published_at(provider_article.published_at)

        article_data = normalize_article(
            company_id=company_id, provider_code=PROVIDER_SOURCE_CODE, article=provider_article
        )
        validate_category(article_data["category"])
        validate_checksum_format(article_data["checksum"])
        validate_required_fields(article_data)

        checksum = article_data["checksum"]
        if checksum in seen_checksums:
            return None, False
        seen_checksums.add(checksum)

        existing = await self._articles.get_by_checksum(checksum)
        if existing is not None:
            return existing, False

        article = await self._articles.create_article(article_data)
        return article, True

    async def _link_to_research_dossier(
        self, company_id: uuid.UUID, symbol: str, synced_articles: list[NewsArticle]
    ) -> None:
        """Records newly synced articles as Research Dossier evidence.

        Sources are attached to the current research version if one
        already exists; version numbering itself stays owned by
        ResearchPipelineService, so this never creates or bumps a research
        version -- only adds evidence to one that already exists.
        """
        if not synced_articles:
            return

        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "news_synced_before_research_version",
                extra={"symbol": symbol, "article_count": len(synced_articles)},
            )
            return

        source_rows = [
            {
                "dossier_id": dossier.id,
                "version_id": latest_version.id,
                "source_type": SOURCE_TYPE_NEWS,
                "reference_table": PROVIDER_SOURCE_TABLE,
                "reference_id": article.id,
                "range_start": article.published_at.date(),
                "range_end": article.published_at.date(),
                "record_count": 1,
            }
            for article in synced_articles
        ]
        await self._dossiers.bulk_create_sources(source_rows)
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_NEWS_SYNCED,
            description=f"{len(synced_articles)} news article(s) synced for '{symbol}'.",
            version_id=latest_version.id,
        )
        await self._articles.commit()

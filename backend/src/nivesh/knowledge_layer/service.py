"""Knowledge Layer service.

Orchestrates gathering already-persisted textual knowledge from across the
platform (companies, corporate_filings, document_intelligence,
news_intelligence, research), building a deterministic text blob for each
unit (normalization.py), skipping units whose content hasn't changed since
the last run (via `content_checksum`, see repository.py's
`get_checksums_by_company`), embedding the rest through the pluggable
`EmbeddingProvider`, persisting the results, and linking one aggregate
Research Dossier evidence row per generation run.

No AI reasoning, no summarization, no report generation, no chunking of
long text into multiple embeddings -- see PROJECT_CONTEXT.md's frozen
architectural decisions and normalization.py's own docstring for why.
`SOURCE_TYPE_KNOWLEDGE_EMBEDDING` is a new constant added to
research/models.py's SourceType catalog for this version (see that
module's own "extend the catalog, not the schema" docstring) -- unlike
SOURCE_TYPE_NEWS/SOURCE_TYPE_TECHNICAL_INDICATOR, it was not pre-reserved
since Sprint 3, because nothing before v0.7 anticipated a Knowledge Layer.
It is linked as a single aggregate source per run (record_count = number
of embeddings written, no date range -- unlike market_data/
technical_indicator, knowledge units have no natural trading-date range),
following the same "high-volume, continuous evidence" aggregate spirit
research/models.py's ResearchSource docstring already documents.

Generation is not auto-chained from any upstream sync task in this version
(unlike technical_intelligence, which auto-chains off
sync_company_market_data) -- deliberately, since knowledge sources span
four different upstream modules (news, filings, document extraction,
research dossier refresh) and each embedding call costs real money;
auto-wiring this from every one of those syncs is a reasonable future step
once that cost profile has been discussed with the user, not assumed here.
See ingestion/tasks.py's generate_knowledge_embeddings docstring.
"""

import logging
import uuid
from dataclasses import dataclass

from nivesh.companies.models import Company
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.repository import CorporateFilingRepository
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.knowledge_layer.models import (
    SOURCE_TABLE_BY_TYPE,
    SOURCE_TYPE_COMPANY_PROFILE,
    SOURCE_TYPE_CORPORATE_FILING,
    SOURCE_TYPE_DOCUMENT_SECTION,
    SOURCE_TYPE_NEWS_ARTICLE,
    SOURCE_TYPE_RESEARCH_SUMMARY,
    KnowledgeEmbedding,
)
from nivesh.knowledge_layer.normalization import (
    KnowledgeUnit,
    build_company_profile_text,
    build_corporate_filing_text,
    build_document_section_text,
    build_news_article_text,
    build_research_summary_text,
    compute_content_checksum,
    truncate_for_embedding,
)
from nivesh.knowledge_layer.providers.base import EmbeddingProvider
from nivesh.knowledge_layer.repository import KnowledgeEmbeddingRepository
from nivesh.knowledge_layer.validation import validate_non_empty_text
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.research.models import SOURCE_TYPE_KNOWLEDGE_EMBEDDING
from nivesh.research.repository import ResearchDossierRepository

logger = logging.getLogger(__name__)

PROVIDER_SOURCE_TABLE = "knowledge_embeddings"
EVENT_TYPE_EMBEDDINGS_GENERATED = "knowledge_embeddings_generated"

# Bounds how many rows per source are fetched and considered in a single
# generation run -- checksums already make repeat scans of unchanged rows
# cheap (no embedding call), this just bounds the read itself, the same
# spirit as technical_intelligence's LOOKBACK_BARS without needing an
# identical mechanism.
MAX_UNITS_PER_SOURCE = 200


@dataclass(frozen=True)
class KnowledgeGenerationResult:
    company_id: uuid.UUID
    symbol: str
    embeddings_generated: int
    embeddings_unchanged: int


@dataclass(frozen=True)
class KnowledgeSearchHit:
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str | None
    content_text: str
    similarity: float


class KnowledgeLayerService:
    def __init__(
        self,
        provider: EmbeddingProvider,
        company_repository: CompanyRepository,
        filing_repository: CorporateFilingRepository,
        extraction_repository: DocumentExtractionRepository,
        article_repository: NewsArticleRepository,
        dossier_repository: ResearchDossierRepository,
        embedding_repository: KnowledgeEmbeddingRepository,
    ) -> None:
        self._provider = provider
        self._companies = company_repository
        self._filings = filing_repository
        self._extractions = extraction_repository
        self._articles = article_repository
        self._dossiers = dossier_repository
        self._embeddings = embedding_repository

    async def generate_embeddings(self, symbol: str) -> KnowledgeGenerationResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        units = await self._gather_units(company)
        existing_checksums = await self._embeddings.get_checksums_by_company(company.id)

        to_embed: list[KnowledgeUnit] = []
        checksums: dict[uuid.UUID, str] = {}
        unchanged = 0
        for unit in units:
            validate_non_empty_text(unit.content_text)
            checksum = compute_content_checksum(unit.content_text)
            checksums[unit.source_id] = checksum
            if existing_checksums.get((unit.source_type, unit.source_id)) == checksum:
                unchanged += 1
                continue
            to_embed.append(unit)

        generated = 0
        if to_embed:
            vectors = await self._provider.embed([unit.content_text for unit in to_embed])
            rows = [
                {
                    "company_id": company.id,
                    "source_type": unit.source_type,
                    "source_table": unit.source_table,
                    "source_id": unit.source_id,
                    "title": unit.title,
                    "content_text": unit.content_text,
                    "content_checksum": checksums[unit.source_id],
                    "embedding": list(vector.vector),
                    "embedding_model": vector.model,
                    "embedding_dimensions": vector.dimensions,
                }
                for unit, vector in zip(to_embed, vectors, strict=True)
            ]
            generated = await self._embeddings.bulk_upsert(rows)

        await self._link_to_research_dossier(company.id, company.symbol, generated, unchanged)

        return KnowledgeGenerationResult(
            company_id=company.id,
            symbol=company.symbol,
            embeddings_generated=generated,
            embeddings_unchanged=unchanged,
        )

    async def search(self, symbol: str, query: str, limit: int = 10) -> list[KnowledgeSearchHit]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        validate_non_empty_text(query)
        vectors = await self._provider.embed([truncate_for_embedding(query)])
        query_vector = list(vectors[0].vector)

        hits = await self._embeddings.search_similar_by_company(
            company.id, query_vector, limit=limit
        )
        return [
            KnowledgeSearchHit(
                source_type=row.source_type,
                source_table=row.source_table,
                source_id=row.source_id,
                title=row.title,
                content_text=row.content_text,
                similarity=1.0 - distance,
            )
            for row, distance in hits
        ]

    async def list_embeddings(
        self, symbol: str, limit: int = 50, offset: int = 0
    ) -> list[KnowledgeEmbedding]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._embeddings.list_by_company(company.id, limit=limit, offset=offset)

    # -- internals -----------------------------------------------------

    async def _gather_units(self, company: Company) -> list[KnowledgeUnit]:
        units: list[KnowledgeUnit] = [
            KnowledgeUnit(
                source_type=SOURCE_TYPE_COMPANY_PROFILE,
                source_table=SOURCE_TABLE_BY_TYPE[SOURCE_TYPE_COMPANY_PROFILE],
                source_id=company.id,
                title=company.name,
                content_text=truncate_for_embedding(
                    build_company_profile_text(
                        symbol=company.symbol,
                        name=company.name,
                        sector=company.sector,
                        industry=company.industry,
                    )
                ),
            )
        ]

        filings = await self._filings.list_by_company(company.id, limit=MAX_UNITS_PER_SOURCE)
        for filing in filings:
            units.append(
                KnowledgeUnit(
                    source_type=SOURCE_TYPE_CORPORATE_FILING,
                    source_table=SOURCE_TABLE_BY_TYPE[SOURCE_TYPE_CORPORATE_FILING],
                    source_id=filing.id,
                    title=filing.title,
                    content_text=truncate_for_embedding(
                        build_corporate_filing_text(
                            title=filing.title,
                            filing_type=filing.filing_type,
                            reporting_period=filing.reporting_period,
                            category_name=filing.category.name,
                        )
                    ),
                )
            )

        extractions = await self._extractions.list_by_company_with_sections(
            company.id, limit=MAX_UNITS_PER_SOURCE
        )
        for extraction in extractions:
            for section in extraction.sections:
                units.append(
                    KnowledgeUnit(
                        source_type=SOURCE_TYPE_DOCUMENT_SECTION,
                        source_table=SOURCE_TABLE_BY_TYPE[SOURCE_TYPE_DOCUMENT_SECTION],
                        source_id=section.id,
                        title=section.heading,
                        content_text=truncate_for_embedding(
                            build_document_section_text(
                                heading=section.heading, content=section.content
                            )
                        ),
                    )
                )

        articles = await self._articles.list_by_company(company.id, limit=MAX_UNITS_PER_SOURCE)
        for article in articles:
            units.append(
                KnowledgeUnit(
                    source_type=SOURCE_TYPE_NEWS_ARTICLE,
                    source_table=SOURCE_TABLE_BY_TYPE[SOURCE_TYPE_NEWS_ARTICLE],
                    source_id=article.id,
                    title=article.title,
                    content_text=truncate_for_embedding(
                        build_news_article_text(title=article.title, summary=article.summary)
                    ),
                )
            )

        dossier = await self._dossiers.get_by_company_id(company.id)
        if dossier is not None:
            versions = await self._dossiers.get_version_history(
                dossier.id, limit=MAX_UNITS_PER_SOURCE
            )
            for version in versions:
                units.append(
                    KnowledgeUnit(
                        source_type=SOURCE_TYPE_RESEARCH_SUMMARY,
                        source_table=SOURCE_TABLE_BY_TYPE[SOURCE_TYPE_RESEARCH_SUMMARY],
                        source_id=version.id,
                        title=f"Research version {version.version_number}",
                        content_text=truncate_for_embedding(
                            build_research_summary_text(change_summary=version.change_summary)
                        ),
                    )
                )

        return units

    async def _link_to_research_dossier(
        self, company_id: uuid.UUID, symbol: str, generated: int, unchanged: int
    ) -> None:
        """Records a newly persisted generation run as one aggregate
        Research Dossier evidence row -- see module docstring for why
        knowledge embeddings are linked as a single aggregate row rather
        than one row per embedding.

        Sources are attached to the current research version if one
        already exists; version numbering itself stays owned by
        ResearchPipelineService, so this never creates or bumps a research
        version -- only adds evidence to one that already exists.
        """
        if generated == 0:
            return

        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "knowledge_embeddings_generated_before_research_version",
                extra={"symbol": symbol, "embedding_count": generated},
            )
            return

        source_rows = [
            {
                "dossier_id": dossier.id,
                "version_id": latest_version.id,
                "source_type": SOURCE_TYPE_KNOWLEDGE_EMBEDDING,
                "reference_table": PROVIDER_SOURCE_TABLE,
                "reference_id": None,
                "range_start": None,
                "range_end": None,
                "record_count": generated,
            }
        ]
        await self._dossiers.bulk_create_sources(source_rows)
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_EMBEDDINGS_GENERATED,
            description=(
                f"{generated} knowledge embedding(s) generated for '{symbol}' "
                f"({unchanged} unchanged, skipped)."
            ),
            version_id=latest_version.id,
        )
        await self._embeddings.commit()

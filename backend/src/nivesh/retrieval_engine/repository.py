"""Retrieval Engine data-access layer.

Unlike every other repository in this codebase, `RetrievalRepository`
queries **no table of its own** -- `retrieval_engine` owns no table (see
models.py). Instead it composes the six sibling repositories that already
own the data this module retrieves (`financials`, `technical_intelligence`,
`corporate_filings`, `document_intelligence`, `news_intelligence`,
`knowledge_layer`), each accessed only through its own existing public
methods -- never a raw query against another module's table. This still
follows the "cross-module reads go through the owning module's repository"
rule (PROJECT_CONTEXT.md §13 point 4); it just means *every* read this
repository makes is a cross-module read, since aggregating already-owned
evidence is this module's entire job. Every method here is read-only.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.corporate_filings.models import CorporateFiling
from nivesh.corporate_filings.repository import CorporateFilingRepository
from nivesh.document_intelligence.models import DocumentExtraction, DocumentSection
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.financials.models import PERIOD_TYPE_ANNUAL, PERIOD_TYPE_QUARTERLY, FinancialStatement
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.knowledge_layer.models import KnowledgeEmbedding
from nivesh.knowledge_layer.repository import KnowledgeEmbeddingRepository
from nivesh.news_intelligence.models import NewsArticle
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.technical_intelligence.models import TechnicalIndicator
from nivesh.technical_intelligence.repository import TechnicalIndicatorRepository


class RetrievalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._financial_statements = FinancialStatementRepository(session)
        self._technical_indicators = TechnicalIndicatorRepository(session)
        self._corporate_filings = CorporateFilingRepository(session)
        self._document_extractions = DocumentExtractionRepository(session)
        self._news_articles = NewsArticleRepository(session)
        self._knowledge_embeddings = KnowledgeEmbeddingRepository(session)

    async def get_financial_statements(
        self, company_id: uuid.UUID, *, annual_limit: int = 2, quarterly_limit: int = 4
    ) -> list[FinancialStatement]:
        annual = await self._financial_statements.list_latest_statements(
            company_id, PERIOD_TYPE_ANNUAL, limit=annual_limit
        )
        quarterly = await self._financial_statements.list_latest_statements(
            company_id, PERIOD_TYPE_QUARTERLY, limit=quarterly_limit
        )
        return [*annual, *quarterly]

    async def get_technical_snapshot(self, company_id: uuid.UUID) -> list[TechnicalIndicator]:
        return await self._technical_indicators.get_latest_snapshot(company_id)

    async def get_corporate_filings(
        self, company_id: uuid.UUID, limit: int = 10
    ) -> list[CorporateFiling]:
        return await self._corporate_filings.list_by_company(company_id, limit=limit)

    async def get_document_sections(
        self, company_id: uuid.UUID, limit: int = 5
    ) -> list[tuple[DocumentExtraction, DocumentSection]]:
        extractions = await self._document_extractions.list_by_company_with_sections(
            company_id, limit=limit
        )
        return [
            (extraction, section) for extraction in extractions for section in extraction.sections
        ]

    async def get_news_articles(self, company_id: uuid.UUID, limit: int = 10) -> list[NewsArticle]:
        return await self._news_articles.list_by_company(company_id, limit=limit)

    async def get_semantic_matches(
        self, company_id: uuid.UUID, query_vector: list[float], limit: int = 10
    ) -> list[tuple[KnowledgeEmbedding, float]]:
        return await self._knowledge_embeddings.search_similar_by_company(
            company_id, query_vector, limit=limit
        )

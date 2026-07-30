"""Retrieval Engine service.

The single evidence-retrieval surface intended for future AI agents
(`ai_agents`, still unimplemented -- see PROJECT_CONTEXT.md §12). This
module is **strictly retrieval, ranking, and packaging** -- it never calls
an LLM, never summarizes, never generates analysis or recommendations. It
composes two retrieval legs for one company:

- **Semantic**: embeds the caller's query (reusing knowledge_layer's own
  `EmbeddingProvider` -- the same OpenAI-backed provider, not a second
  implementation) and runs `KnowledgeEmbeddingRepository`'s cosine-distance
  search, scoped to the company.
- **Structured SQL**: fetches the company's latest financial statements,
  technical indicator snapshot, corporate filings, Document Intelligence
  sections, and news articles directly -- no query text involved, since
  "structured SQL retrieval" is a filter/fetch by identity and recency,
  not a similarity search (see normalization.py's module docstring for
  how both legs land on one comparable relevance scale).

Both legs' results are deduplicated and ranked by
`normalization.deduplicate_and_rank` and returned as one ordered evidence
list, or assembled into a `ContextPackage` (evidence + a deterministic,
citation-annotated text block) for `build_context_package`.

**The semantic leg degrades gracefully.** If the embedding provider fails
(missing/invalid `OPENAI_API_KEY`, a transient OpenAI outage -- anything
raising `EmbeddingProviderError`), `_fetch_all` catches it, logs a
warning, and proceeds with an empty semantic result rather than failing
the whole request -- structured SQL evidence needs no external API and
should never be unavailable because a *different* leg's dependency is
down. A caller can tell this happened from the response alone: no
`retrieved_via=("semantic",)` items will be present.

**Stateless by explicit user decision during v0.8 planning**: no
retrieval call is persisted anywhere (no new table, no migration). The
`inspect_retrieval` method/endpoint exists to give visibility into a
*live* retrieval call (per-source fetch counts, pre- and post-dedup
totals) without needing a stored history to look back on.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from nivesh.companies.models import Company
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.financials.models import FinancialStatement
from nivesh.knowledge_layer.providers.base import EmbeddingProvider
from nivesh.knowledge_layer.providers.exceptions import EmbeddingProviderError
from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_DOCUMENT_SECTION,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
    EVIDENCE_SOURCE_NEWS_ARTICLE,
    EVIDENCE_SOURCE_TECHNICAL_INDICATOR,
    RETRIEVED_VIA_SEMANTIC,
    RETRIEVED_VIA_STRUCTURED,
)
from nivesh.retrieval_engine.normalization import (
    ContextPackage,
    EvidenceItem,
    build_context_package,
    deduplicate_and_rank,
    recency_score,
    semantic_score,
    truncate_query,
    truncate_snippet,
)
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.retrieval_engine.validation import validate_limit, validate_query

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 20
ANNUAL_STATEMENTS_LIMIT = 2
QUARTERLY_STATEMENTS_LIMIT = 4
FILINGS_LIMIT = 10
DOCUMENT_EXTRACTIONS_LIMIT = 5
NEWS_LIMIT = 10
SEMANTIC_LIMIT = 10


@dataclass(frozen=True)
class RetrievalDiagnostics:
    symbol: str
    query: str
    fetched_counts: dict[str, int]
    total_fetched: int
    total_after_dedup: int
    total_returned: int
    evidence: tuple[EvidenceItem, ...]


class RetrievalEngineService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        company_repository: CompanyRepository,
        evidence_repository: RetrievalRepository,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._companies = company_repository
        self._evidence = evidence_repository

    async def retrieve_evidence(
        self, symbol: str, query: str, limit: int = DEFAULT_LIMIT
    ) -> list[EvidenceItem]:
        company = await self._get_company(symbol)
        validate_query(query)
        validate_limit(limit)

        semantic_items, structured_items = await self._fetch_all(company, query)
        return deduplicate_and_rank(semantic_items + structured_items, limit=limit)

    async def build_context_package(
        self, symbol: str, query: str, limit: int = DEFAULT_LIMIT
    ) -> ContextPackage:
        company = await self._get_company(symbol)
        validate_query(query)
        validate_limit(limit)

        semantic_items, structured_items = await self._fetch_all(company, query)
        evidence = deduplicate_and_rank(semantic_items + structured_items, limit=limit)
        return build_context_package(company.symbol, query, evidence)

    async def inspect_retrieval(
        self, symbol: str, query: str, limit: int = DEFAULT_LIMIT
    ) -> RetrievalDiagnostics:
        company = await self._get_company(symbol)
        validate_query(query)
        validate_limit(limit)

        semantic_items, structured_items = await self._fetch_all(company, query)
        fetched_counts = {
            "semantic": len(semantic_items),
            EVIDENCE_SOURCE_FINANCIAL_STATEMENT: sum(
                1
                for item in structured_items
                if item.source_type == EVIDENCE_SOURCE_FINANCIAL_STATEMENT
            ),
            EVIDENCE_SOURCE_TECHNICAL_INDICATOR: sum(
                1
                for item in structured_items
                if item.source_type == EVIDENCE_SOURCE_TECHNICAL_INDICATOR
            ),
            EVIDENCE_SOURCE_CORPORATE_FILING: sum(
                1
                for item in structured_items
                if item.source_type == EVIDENCE_SOURCE_CORPORATE_FILING
            ),
            EVIDENCE_SOURCE_DOCUMENT_SECTION: sum(
                1
                for item in structured_items
                if item.source_type == EVIDENCE_SOURCE_DOCUMENT_SECTION
            ),
            EVIDENCE_SOURCE_NEWS_ARTICLE: sum(
                1 for item in structured_items if item.source_type == EVIDENCE_SOURCE_NEWS_ARTICLE
            ),
        }
        combined = semantic_items + structured_items
        ranked = deduplicate_and_rank(combined, limit=limit)
        return RetrievalDiagnostics(
            symbol=company.symbol,
            query=query,
            fetched_counts=fetched_counts,
            total_fetched=len(combined),
            total_after_dedup=len({(item.source_type, item.source_id) for item in combined}),
            total_returned=len(ranked),
            evidence=tuple(ranked),
        )

    # -- internals -----------------------------------------------------

    async def _get_company(self, symbol: str) -> Company:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return company

    async def _fetch_all(
        self, company: Company, query: str
    ) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
        try:
            semantic_items = await self._semantic_evidence(company.id, query)
        except EmbeddingProviderError:
            logger.warning(
                "retrieval_semantic_leg_failed",
                extra={"symbol": company.symbol},
                exc_info=True,
            )
            semantic_items = []

        structured_items = [
            *(await self._financial_evidence(company.id)),
            *(await self._technical_evidence(company.id)),
            *(await self._filing_evidence(company.id)),
            *(await self._document_evidence(company.id)),
            *(await self._news_evidence(company.id)),
        ]
        return semantic_items, structured_items

    async def _semantic_evidence(self, company_id: uuid.UUID, query: str) -> list[EvidenceItem]:
        """The semantic leg's own failure never fails the whole request --
        `_fetch_all` catches `EmbeddingProviderError` around this call so
        structured SQL evidence (which needs no external API) is still
        returned even if the embedding provider is unavailable or
        misconfigured. See `_fetch_all` and this module's docstring.
        """
        vectors = await self._embedding_provider.embed([truncate_query(query)])
        query_vector = list(vectors[0].vector)
        hits = await self._evidence.get_semantic_matches(
            company_id, query_vector, limit=SEMANTIC_LIMIT
        )
        return [
            EvidenceItem(
                source_type=row.source_type,
                source_table=row.source_table,
                source_id=row.source_id,
                title=row.title or row.source_type,
                snippet=truncate_snippet(row.content_text),
                evidence_date=row.updated_at.date(),
                relevance_score=semantic_score(distance),
                retrieved_via=(RETRIEVED_VIA_SEMANTIC,),
            )
            for row, distance in hits
        ]

    async def _financial_evidence(self, company_id: uuid.UUID) -> list[EvidenceItem]:
        as_of = datetime.now(UTC).date()
        statements = await self._evidence.get_financial_statements(
            company_id,
            annual_limit=ANNUAL_STATEMENTS_LIMIT,
            quarterly_limit=QUARTERLY_STATEMENTS_LIMIT,
        )
        return [
            EvidenceItem(
                source_type=EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
                source_table="financial_statements",
                source_id=statement.id,
                title=(
                    f"{statement.period_type.capitalize()} statement "
                    f"{statement.fiscal_period} FY{statement.fiscal_year}"
                ),
                snippet=truncate_snippet(_financial_statement_snippet(statement)),
                evidence_date=statement.period_end_date,
                relevance_score=recency_score(statement.period_end_date, as_of),
                retrieved_via=(RETRIEVED_VIA_STRUCTURED,),
            )
            for statement in statements
        ]

    async def _technical_evidence(self, company_id: uuid.UUID) -> list[EvidenceItem]:
        as_of = datetime.now(UTC).date()
        indicators = await self._evidence.get_technical_snapshot(company_id)
        if not indicators:
            return []

        latest_date = max(indicator.trading_date for indicator in indicators)
        snippet = ", ".join(
            f"{indicator.indicator_name}={indicator.indicator_value}"
            for indicator in sorted(indicators, key=lambda i: i.indicator_name)
        )
        return [
            EvidenceItem(
                source_type=EVIDENCE_SOURCE_TECHNICAL_INDICATOR,
                source_table="technical_indicators",
                source_id=company_id,
                title="Latest technical indicator snapshot",
                snippet=truncate_snippet(snippet),
                evidence_date=latest_date,
                relevance_score=recency_score(latest_date, as_of),
                retrieved_via=(RETRIEVED_VIA_STRUCTURED,),
            )
        ]

    async def _filing_evidence(self, company_id: uuid.UUID) -> list[EvidenceItem]:
        as_of = datetime.now(UTC).date()
        filings = await self._evidence.get_corporate_filings(company_id, limit=FILINGS_LIMIT)
        return [
            EvidenceItem(
                source_type=EVIDENCE_SOURCE_CORPORATE_FILING,
                source_table="corporate_filings",
                source_id=filing.id,
                title=filing.title,
                snippet=truncate_snippet(
                    f"{filing.category.name} filing ({filing.filing_type}, "
                    f"reporting period {filing.reporting_period})."
                ),
                evidence_date=filing.filing_date,
                relevance_score=recency_score(filing.filing_date, as_of),
                retrieved_via=(RETRIEVED_VIA_STRUCTURED,),
            )
            for filing in filings
        ]

    async def _document_evidence(self, company_id: uuid.UUID) -> list[EvidenceItem]:
        as_of = datetime.now(UTC).date()
        pairs = await self._evidence.get_document_sections(
            company_id, limit=DOCUMENT_EXTRACTIONS_LIMIT
        )
        return [
            EvidenceItem(
                source_type=EVIDENCE_SOURCE_DOCUMENT_SECTION,
                source_table="document_sections",
                source_id=section.id,
                title=section.heading,
                snippet=truncate_snippet(section.content),
                evidence_date=extraction.created_at.date(),
                relevance_score=recency_score(extraction.created_at.date(), as_of),
                retrieved_via=(RETRIEVED_VIA_STRUCTURED,),
            )
            for extraction, section in pairs
        ]

    async def _news_evidence(self, company_id: uuid.UUID) -> list[EvidenceItem]:
        as_of = datetime.now(UTC).date()
        articles = await self._evidence.get_news_articles(company_id, limit=NEWS_LIMIT)
        return [
            EvidenceItem(
                source_type=EVIDENCE_SOURCE_NEWS_ARTICLE,
                source_table="news_articles",
                source_id=article.id,
                title=article.title,
                snippet=truncate_snippet(article.summary),
                evidence_date=article.published_at.date(),
                relevance_score=recency_score(article.published_at.date(), as_of),
                retrieved_via=(RETRIEVED_VIA_STRUCTURED,),
            )
            for article in articles
        ]


def _financial_statement_snippet(statement: FinancialStatement) -> str:
    parts = [f"{statement.currency} statement, version {statement.version}."]
    if statement.profit_and_loss is not None:
        pnl = statement.profit_and_loss
        parts.append(f"Revenue: {pnl.total_revenue}, Net income: {pnl.net_income}.")
    if statement.balance_sheet is not None:
        bs = statement.balance_sheet
        parts.append(f"Total assets: {bs.total_assets}, Total equity: {bs.total_equity}.")
    if statement.ratio is not None and statement.ratio.return_on_equity is not None:
        parts.append(f"ROE: {statement.ratio.return_on_equity}.")
    return " ".join(parts)

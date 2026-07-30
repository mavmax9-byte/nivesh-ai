from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import CorporateFiling, FilingCategory
from nivesh.document_intelligence.models import DocumentExtraction, DocumentSection
from nivesh.financials.models import (
    PERIOD_TYPE_QUARTERLY,
    FinancialStatement,
    ProfitAndLoss,
)
from nivesh.knowledge_layer.models import KnowledgeEmbedding
from nivesh.knowledge_layer.providers.base import ProviderEmbedding
from nivesh.knowledge_layer.providers.exceptions import EmbeddingProviderError
from nivesh.news_intelligence.models import NewsArticle
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.retrieval_engine.service import RetrievalEngineService
from nivesh.technical_intelligence.models import TechnicalIndicator


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(),
        symbol=symbol,
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )
    company.exchange = exchange
    return company


def _make_service(
    company,
    *,
    semantic_hits=None,
    statements=None,
    indicators=None,
    filings=None,
    document_pairs=None,
    articles=None,
):
    embedding_provider = AsyncMock()
    embedding_provider.embed.return_value = [
        ProviderEmbedding(vector=(0.1, 0.2, 0.3), model="text-embedding-3-small", dimensions=3)
    ]

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    evidence_repository = AsyncMock(spec=RetrievalRepository)
    evidence_repository.get_semantic_matches.return_value = semantic_hits or []
    evidence_repository.get_financial_statements.return_value = statements or []
    evidence_repository.get_technical_snapshot.return_value = indicators or []
    evidence_repository.get_corporate_filings.return_value = filings or []
    evidence_repository.get_document_sections.return_value = document_pairs or []
    evidence_repository.get_news_articles.return_value = articles or []

    service = RetrievalEngineService(
        embedding_provider=embedding_provider,
        company_repository=company_repository,
        evidence_repository=evidence_repository,
    )
    return service, embedding_provider, evidence_repository


@pytest.mark.asyncio
async def test_retrieve_evidence_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = RetrievalEngineService(
        embedding_provider=AsyncMock(),
        company_repository=company_repository,
        evidence_repository=AsyncMock(),
    )
    with pytest.raises(NotFoundError):
        await service.retrieve_evidence("NOPE", "query")


@pytest.mark.asyncio
async def test_retrieve_evidence_combines_and_ranks_all_sources():
    company = _company()

    category = FilingCategory(id=uuid4(), code="financial_results", name="Financial Results")
    filing = CorporateFiling(
        id=uuid4(),
        company_id=company.id,
        exchange="NSE",
        filing_type="quarterly_results",
        category_id=category.id,
        source_id=uuid4(),
        title="Q1 FY26 Results",
        reporting_period="Q1FY26",
        filing_date=date(2026, 7, 1),
        source_url="https://example.com",
        checksum="a" * 64,
    )
    filing.category = category

    statement = FinancialStatement(
        id=uuid4(),
        company_id=company.id,
        period_type=PERIOD_TYPE_QUARTERLY,
        fiscal_year=2026,
        fiscal_period="Q1",
        period_end_date=date(2026, 6, 30),
        currency="INR",
        version=1,
        source="yfinance-dev",
    )
    statement.profit_and_loss = ProfitAndLoss(
        id=uuid4(),
        financial_statement_id=statement.id,
        total_revenue=1000,
        net_income=200,
    )
    statement.balance_sheet = None
    statement.ratio = None

    indicator = TechnicalIndicator(
        id=uuid4(),
        company_id=company.id,
        trading_date=date(2026, 7, 28),
        indicator_name="rsi_14",
        indicator_parameters={},
        indicator_value=55.5,
        calculation_timestamp=datetime(2026, 7, 28, tzinfo=UTC),
    )

    extraction = DocumentExtraction(
        id=uuid4(),
        filing_version_id=uuid4(),
        company_id=company.id,
        extraction_status="completed",
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="full text",
        page_count=1,
        section_count=1,
    )
    extraction.created_at = datetime(2026, 7, 20, tzinfo=UTC)
    section = DocumentSection(
        id=uuid4(),
        document_extraction_id=extraction.id,
        sequence=0,
        heading="Risk Factors",
        level=1,
        page_number=1,
        content="Market risk is elevated.",
    )

    article = NewsArticle(
        id=uuid4(),
        company_id=company.id,
        title="TCS beats estimates",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 25, tzinfo=UTC),
        url="https://example.com/story",
        summary="Revenue rose.",
        full_content=None,
        language="en",
        category="earnings",
        provider="yfinance-dev",
        checksum="b" * 64,
    )

    semantic_hit_row = KnowledgeEmbedding(
        id=uuid4(),
        company_id=company.id,
        source_type="research_summary",
        source_table="research_versions",
        source_id=uuid4(),
        title="Research version 1",
        content_text="Initial research version summary.",
        content_checksum="c" * 64,
        embedding=[0.1, 0.2, 0.3],
        embedding_model="text-embedding-3-small",
        embedding_dimensions=3,
    )
    semantic_hit_row.updated_at = datetime(2026, 7, 29, tzinfo=UTC)

    service, embedding_provider, evidence_repository = _make_service(
        company,
        semantic_hits=[(semantic_hit_row, 0.1)],
        statements=[statement],
        indicators=[indicator],
        filings=[filing],
        document_pairs=[(extraction, section)],
        articles=[article],
    )

    evidence = await service.retrieve_evidence("TCS", "revenue growth", limit=20)

    source_types = {item.source_type for item in evidence}
    assert source_types == {
        "research_summary",
        "financial_statement",
        "technical_indicator",
        "corporate_filing",
        "document_section",
        "news_article",
    }
    assert len(evidence) == 6
    # ranked descending by relevance_score
    assert all(
        evidence[i].relevance_score >= evidence[i + 1].relevance_score
        for i in range(len(evidence) - 1)
    )
    embedding_provider.embed.assert_awaited_once()


@pytest.mark.asyncio
async def test_retrieve_evidence_degrades_gracefully_when_semantic_leg_fails():
    company = _company()
    article = NewsArticle(
        id=uuid4(),
        company_id=company.id,
        title="TCS beats estimates",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 25, tzinfo=UTC),
        url="https://example.com/story",
        summary="Revenue rose.",
        full_content=None,
        language="en",
        category="earnings",
        provider="yfinance-dev",
        checksum="b" * 64,
    )
    service, embedding_provider, _ = _make_service(company, articles=[article])
    embedding_provider.embed.side_effect = EmbeddingProviderError("no API key configured")

    evidence = await service.retrieve_evidence("TCS", "revenue growth", limit=20)

    assert len(evidence) == 1
    assert evidence[0].source_type == "news_article"
    assert evidence[0].retrieved_via == ("structured",)


@pytest.mark.asyncio
async def test_build_context_package_returns_text_and_evidence():
    company = _company()
    article = NewsArticle(
        id=uuid4(),
        company_id=company.id,
        title="TCS beats estimates",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 25, tzinfo=UTC),
        url="https://example.com/story",
        summary="Revenue rose.",
        full_content=None,
        language="en",
        category="earnings",
        provider="yfinance-dev",
        checksum="b" * 64,
    )
    service, *_ = _make_service(company, articles=[article])

    package = await service.build_context_package("TCS", "revenue", limit=10)

    assert package.symbol == "TCS"
    assert len(package.evidence) == 1
    assert "TCS beats estimates" in package.context_text


@pytest.mark.asyncio
async def test_inspect_retrieval_reports_fetch_counts():
    company = _company()
    article = NewsArticle(
        id=uuid4(),
        company_id=company.id,
        title="TCS beats estimates",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 25, tzinfo=UTC),
        url="https://example.com/story",
        summary="Revenue rose.",
        full_content=None,
        language="en",
        category="earnings",
        provider="yfinance-dev",
        checksum="b" * 64,
    )
    service, *_ = _make_service(company, articles=[article])

    diagnostics = await service.inspect_retrieval("TCS", "revenue", limit=10)

    assert diagnostics.fetched_counts["news_article"] == 1
    assert diagnostics.total_fetched == 1
    assert diagnostics.total_after_dedup == 1
    assert diagnostics.total_returned == 1

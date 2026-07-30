"""Repository tests against a real PostgreSQL test database.

`RetrievalRepository` owns no table of its own (see models.py) -- these
tests exercise its delegation to each sibling repository, seeding rows
directly via the ORM (bypassing each module's own write-side service
logic, which is already covered by that module's own tests) and checking
`RetrievalRepository`'s read methods surface them correctly, especially
the document-section flattening `get_document_sections` performs.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.corporate_filings.models import (
    CorporateFiling,
    FilingCategory,
    FilingSource,
    FilingVersion,
)
from nivesh.document_intelligence.models import DocumentExtraction, DocumentSection
from nivesh.financials.models import PERIOD_TYPE_QUARTERLY, FinancialStatement
from nivesh.knowledge_layer.models import KnowledgeEmbedding
from nivesh.news_intelligence.models import NewsArticle
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.technical_intelligence.models import TechnicalIndicator

_DIMENSIONS = 1536


async def _make_company(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    exchange = await exchange_repository.get_or_create_by_code("NSE")
    return await company_repository.upsert(
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )


@pytest.mark.asyncio
async def test_get_financial_statements_returns_annual_and_quarterly(db_session):
    company = await _make_company(db_session)
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
    db_session.add(statement)
    await db_session.commit()

    repository = RetrievalRepository(db_session)
    statements = await repository.get_financial_statements(company.id)

    assert len(statements) == 1
    assert statements[0].fiscal_period == "Q1"


@pytest.mark.asyncio
async def test_get_technical_snapshot_returns_latest_indicators(db_session):
    company = await _make_company(db_session)
    indicator = TechnicalIndicator(
        id=uuid4(),
        company_id=company.id,
        trading_date=date(2026, 7, 28),
        indicator_name="rsi_14",
        indicator_parameters={},
        indicator_value=55.5,
        calculation_timestamp=datetime(2026, 7, 28, tzinfo=UTC),
    )
    db_session.add(indicator)
    await db_session.commit()

    repository = RetrievalRepository(db_session)
    indicators = await repository.get_technical_snapshot(company.id)

    assert len(indicators) == 1
    assert indicators[0].indicator_name == "rsi_14"


@pytest.mark.asyncio
async def test_get_corporate_filings_returns_companys_filings(db_session):
    company = await _make_company(db_session)
    category = FilingCategory(id=uuid4(), code="financial_results", name="Financial Results")
    source = FilingSource(id=uuid4(), code="yfinance-dev", name="yfinance (dev)")
    db_session.add_all([category, source])
    await db_session.flush()

    filing = CorporateFiling(
        id=uuid4(),
        company_id=company.id,
        exchange="NSE",
        filing_type="quarterly_results",
        category_id=category.id,
        source_id=source.id,
        title="Q1 FY26 Results",
        reporting_period="Q1FY26",
        filing_date=date(2026, 7, 1),
        source_url="https://example.com",
        checksum="a" * 64,
    )
    db_session.add(filing)
    await db_session.commit()

    repository = RetrievalRepository(db_session)
    filings = await repository.get_corporate_filings(company.id)

    assert len(filings) == 1
    assert filings[0].title == "Q1 FY26 Results"
    assert filings[0].category.name == "Financial Results"


@pytest.mark.asyncio
async def test_get_document_sections_flattens_extractions_and_sections(db_session):
    company = await _make_company(db_session)
    category = FilingCategory(id=uuid4(), code="financial_results", name="Financial Results")
    source = FilingSource(id=uuid4(), code="yfinance-dev", name="yfinance (dev)")
    db_session.add_all([category, source])
    await db_session.flush()

    filing = CorporateFiling(
        id=uuid4(),
        company_id=company.id,
        exchange="NSE",
        filing_type="annual_report",
        category_id=category.id,
        source_id=source.id,
        title="Annual Report FY26",
        reporting_period="FY26",
        filing_date=date(2026, 5, 1),
        source_url="https://example.com/annual",
        checksum="b" * 64,
    )
    db_session.add(filing)
    await db_session.flush()

    version = FilingVersion(
        id=uuid4(),
        filing_id=filing.id,
        company_id=company.id,
        version_number=1,
        title=filing.title,
        filing_date=filing.filing_date,
        source_url=filing.source_url,
        checksum=filing.checksum,
    )
    db_session.add(version)
    await db_session.flush()

    extraction = DocumentExtraction(
        id=uuid4(),
        filing_version_id=version.id,
        company_id=company.id,
        extraction_status="completed",
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="full text",
        page_count=1,
        section_count=2,
    )
    db_session.add(extraction)
    await db_session.flush()

    sections = [
        DocumentSection(
            id=uuid4(),
            document_extraction_id=extraction.id,
            sequence=index,
            heading=f"Section {index}",
            level=1,
            page_number=1,
            content=f"Content {index}",
        )
        for index in range(2)
    ]
    db_session.add_all(sections)
    await db_session.commit()

    repository = RetrievalRepository(db_session)
    pairs = await repository.get_document_sections(company.id)

    assert len(pairs) == 2
    assert {section.heading for _extraction, section in pairs} == {"Section 0", "Section 1"}
    assert all(extraction.id == pairs[0][0].id for extraction, _section in pairs)


@pytest.mark.asyncio
async def test_get_news_articles_returns_companys_articles(db_session):
    company = await _make_company(db_session)
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
        checksum="c" * 64,
    )
    db_session.add(article)
    await db_session.commit()

    repository = RetrievalRepository(db_session)
    articles = await repository.get_news_articles(company.id)

    assert len(articles) == 1
    assert articles[0].title == "TCS beats estimates"


@pytest.mark.asyncio
async def test_get_semantic_matches_returns_closest_by_cosine_distance(db_session):
    company = await _make_company(db_session)
    vector = [0.0] * _DIMENSIONS
    vector[0] = 1.0
    embedding = KnowledgeEmbedding(
        id=uuid4(),
        company_id=company.id,
        source_type="news_article",
        source_table="news_articles",
        source_id=uuid4(),
        title="TCS beats estimates",
        content_text="TCS beats estimates. Revenue rose.",
        content_checksum="d" * 64,
        embedding=vector,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=_DIMENSIONS,
    )
    db_session.add(embedding)
    await db_session.commit()

    repository = RetrievalRepository(db_session)
    hits = await repository.get_semantic_matches(company.id, vector, limit=5)

    assert len(hits) == 1
    row, distance = hits[0]
    assert row.title == "TCS beats estimates"
    assert distance == pytest.approx(0.0, abs=1e-6)

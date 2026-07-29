from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import CorporateFiling, FilingCategory
from nivesh.document_intelligence.models import DocumentExtraction, DocumentSection
from nivesh.knowledge_layer.models import KnowledgeEmbedding
from nivesh.knowledge_layer.normalization import (
    build_company_profile_text,
    compute_content_checksum,
    truncate_for_embedding,
)
from nivesh.knowledge_layer.providers.base import ProviderEmbedding
from nivesh.knowledge_layer.service import KnowledgeLayerService
from nivesh.news_intelligence.models import NewsArticle
from nivesh.research.models import CompanyResearchDossier, ResearchVersion


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


def _profile_checksum(company: Company) -> str:
    text = truncate_for_embedding(
        build_company_profile_text(
            symbol=company.symbol,
            name=company.name,
            sector=company.sector,
            industry=company.industry,
        )
    )
    return compute_content_checksum(text)


def _make_service(
    company: Company,
    *,
    filings=None,
    extractions=None,
    articles=None,
    dossier=None,
    latest_research_version=None,
    version_history=None,
    existing_checksums=None,
):
    provider = AsyncMock()

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    filing_repository = AsyncMock()
    filing_repository.list_by_company.return_value = filings or []

    extraction_repository = AsyncMock()
    extraction_repository.list_by_company_with_sections.return_value = extractions or []

    article_repository = AsyncMock()
    article_repository.list_by_company.return_value = articles or []

    dossier_repository = AsyncMock()
    dossier_repository.get_by_company_id.return_value = dossier
    dossier_repository.get_version_history.return_value = version_history or []
    dossier_repository.get_or_create_dossier.return_value = dossier or CompanyResearchDossier(
        id=uuid4(), company_id=company.id
    )
    dossier_repository.get_latest_version.return_value = latest_research_version

    embedding_repository = AsyncMock()
    embedding_repository.get_checksums_by_company.return_value = existing_checksums or {}
    embedding_repository.bulk_upsert.side_effect = lambda rows: len(rows)

    service = KnowledgeLayerService(
        provider=provider,
        company_repository=company_repository,
        filing_repository=filing_repository,
        extraction_repository=extraction_repository,
        article_repository=article_repository,
        dossier_repository=dossier_repository,
        embedding_repository=embedding_repository,
    )
    return (
        service,
        provider,
        company_repository,
        filing_repository,
        extraction_repository,
        article_repository,
        dossier_repository,
        embedding_repository,
    )


def _empty_service() -> KnowledgeLayerService:
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    return KnowledgeLayerService(
        provider=AsyncMock(),
        company_repository=company_repository,
        filing_repository=AsyncMock(),
        extraction_repository=AsyncMock(),
        article_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
        embedding_repository=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_generate_embeddings_raises_not_found_for_unknown_symbol():
    with pytest.raises(NotFoundError):
        await _empty_service().generate_embeddings("NOPE")


@pytest.mark.asyncio
async def test_generate_embeddings_embeds_company_profile_when_nothing_else_exists():
    company = _company()
    version = ResearchVersion(id=uuid4(), dossier_id=uuid4(), version_number=1)
    service, provider, *_, dossier_repository, embedding_repository = _make_service(
        company, latest_research_version=version
    )
    provider.embed.return_value = [
        ProviderEmbedding(vector=(0.1, 0.1, 0.1), model="text-embedding-3-small", dimensions=3)
    ]

    result = await service.generate_embeddings("TCS")

    assert result.embeddings_generated == 1
    assert result.embeddings_unchanged == 0
    embedding_repository.bulk_upsert.assert_awaited_once()
    (rows,) = embedding_repository.bulk_upsert.await_args.args
    assert rows[0]["source_type"] == "company_profile"
    assert rows[0]["source_id"] == company.id

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert source_rows[0]["source_type"] == "knowledge_embedding"
    assert source_rows[0]["record_count"] == 1


@pytest.mark.asyncio
async def test_generate_embeddings_skips_unchanged_content():
    company = _company()
    checksum = _profile_checksum(company)
    service, provider, *_, embedding_repository = _make_service(
        company, existing_checksums={("company_profile", company.id): checksum}
    )

    result = await service.generate_embeddings("TCS")

    assert result.embeddings_generated == 0
    assert result.embeddings_unchanged == 1
    provider.embed.assert_not_awaited()
    embedding_repository.bulk_upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_embeddings_gathers_all_source_types():
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
    section = DocumentSection(
        id=uuid4(),
        document_extraction_id=extraction.id,
        sequence=0,
        heading="Risk Factors",
        level=1,
        page_number=1,
        content="Market risk is elevated.",
    )
    extraction.sections = [section]

    article = NewsArticle(
        id=uuid4(),
        company_id=company.id,
        title="TCS beats estimates",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 10, tzinfo=UTC),
        url="https://example.com/story",
        summary="Revenue rose.",
        full_content=None,
        language="en",
        category="earnings",
        provider="yfinance-dev",
        checksum="b" * 64,
    )

    dossier = CompanyResearchDossier(id=uuid4(), company_id=company.id)
    version = ResearchVersion(
        id=uuid4(),
        dossier_id=dossier.id,
        version_number=1,
        triggered_by="manual",
        change_summary="Initial research version.",
    )

    service, provider, *_, embedding_repository = _make_service(
        company,
        filings=[filing],
        extractions=[extraction],
        articles=[article],
        dossier=dossier,
        version_history=[version],
        latest_research_version=version,
    )
    provider.embed.side_effect = lambda texts: [
        ProviderEmbedding(vector=(0.1, 0.1, 0.1), model="text-embedding-3-small", dimensions=3)
        for _ in texts
    ]

    result = await service.generate_embeddings("TCS")

    assert result.embeddings_generated == 5  # profile + filing + section + article + summary
    (rows,) = embedding_repository.bulk_upsert.await_args.args
    source_types = {row["source_type"] for row in rows}
    assert source_types == {
        "company_profile",
        "corporate_filing",
        "document_section",
        "news_article",
        "research_summary",
    }


@pytest.mark.asyncio
async def test_generate_embeddings_no_dossier_evidence_when_generated_is_zero():
    company = _company()
    checksum = _profile_checksum(company)
    service, provider, *_, dossier_repository, embedding_repository = _make_service(company)
    embedding_repository.get_checksums_by_company.return_value = {
        ("company_profile", company.id): checksum
    }

    result = await service.generate_embeddings("TCS")

    assert result.embeddings_generated == 0
    dossier_repository.get_or_create_dossier.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_embeddings_skips_evidence_when_no_research_version_exists():
    company = _company()
    service, provider, *_, dossier_repository, embedding_repository = _make_service(
        company, latest_research_version=None
    )
    provider.embed.return_value = [
        ProviderEmbedding(vector=(0.1, 0.1, 0.1), model="text-embedding-3-small", dimensions=3)
    ]

    result = await service.generate_embeddings("TCS")

    assert result.embeddings_generated == 1
    dossier_repository.get_or_create_dossier.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_raises_not_found_for_unknown_symbol():
    with pytest.raises(NotFoundError):
        await _empty_service().search("NOPE", "query")


@pytest.mark.asyncio
async def test_search_embeds_query_and_converts_distance_to_similarity():
    company = _company()
    service, provider, *_, embedding_repository = _make_service(company)
    provider.embed.return_value = [
        ProviderEmbedding(vector=(0.5, 0.5), model="text-embedding-3-small", dimensions=2)
    ]
    hit_row = KnowledgeEmbedding(
        id=uuid4(),
        company_id=company.id,
        source_type="news_article",
        source_table="news_articles",
        source_id=uuid4(),
        title="TCS beats estimates",
        content_text="TCS beats estimates. Revenue rose.",
        content_checksum="x" * 64,
        embedding=[0.5, 0.5],
        embedding_model="text-embedding-3-small",
        embedding_dimensions=2,
    )
    embedding_repository.search_similar_by_company.return_value = [(hit_row, 0.1)]

    results = await service.search("TCS", "revenue growth", limit=5)

    assert len(results) == 1
    assert results[0].similarity == pytest.approx(0.9)
    assert results[0].source_type == "news_article"
    embedding_repository.search_similar_by_company.assert_awaited_once_with(
        company.id, [0.5, 0.5], limit=5
    )


@pytest.mark.asyncio
async def test_list_embeddings_delegates_to_repository():
    company = _company()
    service, *_, embedding_repository = _make_service(company)
    embedding_repository.list_by_company.return_value = []

    await service.list_embeddings("TCS")

    embedding_repository.list_by_company.assert_awaited_once_with(company.id, limit=50, offset=0)

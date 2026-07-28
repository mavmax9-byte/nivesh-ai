from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.news_intelligence.models import NewsArticle
from nivesh.news_intelligence.providers.base import ProviderNewsArticle
from nivesh.news_intelligence.service import NewsIntelligenceService
from nivesh.news_intelligence.validation import InvalidNewsDataError
from nivesh.research.models import CompanyResearchDossier, ResearchVersion


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


def _provider_article(**overrides) -> ProviderNewsArticle:
    defaults: dict = dict(
        title="India's TCS rises after quarterly revenue beat",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 10, 3, 56, 27, tzinfo=UTC),
        url="https://sg.finance.yahoo.com/news/indias-tcs-rises-quarterly-revenue.html",
        summary="TCS shares rose after reporting quarterly revenue ahead of estimates.",
        full_content=None,
        language="en",
    )
    defaults.update(overrides)
    return ProviderNewsArticle(**defaults)


def _make_service(
    company,
    *,
    existing_article=None,
    latest_research_version=None,
):
    provider = AsyncMock()

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    article_repository = AsyncMock()
    article_repository.get_by_checksum.return_value = existing_article
    article_repository.create_article.side_effect = lambda data: NewsArticle(id=uuid4(), **data)

    dossier_repository = AsyncMock()
    dossier_repository.get_or_create_dossier.return_value = CompanyResearchDossier(
        id=uuid4(), company_id=company.id
    )
    dossier_repository.get_latest_version.return_value = latest_research_version

    service = NewsIntelligenceService(
        provider=provider,
        company_repository=company_repository,
        article_repository=article_repository,
        dossier_repository=dossier_repository,
    )
    return service, provider, article_repository, dossier_repository


@pytest.mark.asyncio
async def test_sync_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None

    service = NewsIntelligenceService(
        provider=AsyncMock(),
        company_repository=company_repository,
        article_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.sync_company_news("NOPE")


@pytest.mark.asyncio
async def test_sync_creates_new_articles_and_links_dossier():
    company = _company()
    version = ResearchVersion(id=uuid4(), dossier_id=uuid4(), version_number=1)
    service, provider, article_repository, dossier_repository = _make_service(
        company, latest_research_version=version
    )
    provider.get_news.return_value = [_provider_article()]

    result = await service.sync_company_news("TCS")

    assert result.articles_synced == 1
    assert result.articles_unchanged == 0

    article_repository.create_article.assert_awaited_once()
    (create_data,) = article_repository.create_article.await_args.args
    assert create_data["title"] == "India's TCS rises after quarterly revenue beat"
    assert create_data["provider"] == "yfinance-dev"

    article_repository.commit.assert_awaited()

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert len(source_rows) == 1
    assert source_rows[0]["source_type"] == "news"
    assert source_rows[0]["version_id"] == version.id

    dossier_repository.create_timeline_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_skips_article_already_stored_by_checksum():
    company = _company()
    existing = NewsArticle(
        id=uuid4(),
        company_id=company.id,
        title="Already synced",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 10, tzinfo=UTC),
        url="https://example.com/story",
        summary="",
        full_content=None,
        language="en",
        category="general",
        provider="yfinance-dev",
        checksum="a" * 64,
    )
    service, provider, article_repository, dossier_repository = _make_service(
        company, existing_article=existing
    )
    provider.get_news.return_value = [_provider_article()]

    result = await service.sync_company_news("TCS")

    assert result.articles_synced == 0
    assert result.articles_unchanged == 1
    article_repository.create_article.assert_not_awaited()
    dossier_repository.get_or_create_dossier.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_skips_in_batch_duplicate_articles():
    company = _company()
    service, provider, article_repository, _ = _make_service(company)
    duplicate = _provider_article()
    provider.get_news.return_value = [duplicate, duplicate]

    result = await service.sync_company_news("TCS")

    assert result.articles_synced == 1
    assert result.articles_unchanged == 1
    article_repository.create_article.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_does_not_attach_evidence_when_no_research_version_exists_yet():
    company = _company()
    service, provider, article_repository, dossier_repository = _make_service(
        company, latest_research_version=None
    )
    provider.get_news.return_value = [_provider_article()]

    result = await service.sync_company_news("TCS")

    assert result.articles_synced == 1
    dossier_repository.get_or_create_dossier.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_rejects_invalid_url():
    company = _company()
    service, provider, article_repository, _ = _make_service(company)
    provider.get_news.return_value = [_provider_article(url="not-a-url")]

    with pytest.raises(InvalidNewsDataError):
        await service.sync_company_news("TCS")

    article_repository.create_article.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_rejects_naive_published_at():
    company = _company()
    service, provider, article_repository, _ = _make_service(company)
    provider.get_news.return_value = [
        _provider_article(published_at=datetime(2026, 7, 10, 3, 56, 27))  # noqa: DTZ001
    ]

    with pytest.raises(InvalidNewsDataError):
        await service.sync_company_news("TCS")

    article_repository.create_article.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_news_delegates_to_repository():
    company = _company()
    service, _, article_repository, _ = _make_service(company)
    article_repository.list_by_company.return_value = []

    await service.get_news("TCS")

    article_repository.list_by_company.assert_awaited_once_with(company.id, limit=50, offset=0)


@pytest.mark.asyncio
async def test_get_news_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = NewsIntelligenceService(
        provider=AsyncMock(),
        company_repository=company_repository,
        article_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.get_news("NOPE")


@pytest.mark.asyncio
async def test_get_news_by_category_delegates_to_repository():
    company = _company()
    service, _, article_repository, _ = _make_service(company)
    article_repository.list_by_category.return_value = []

    await service.get_news_by_category("TCS", "earnings")

    article_repository.list_by_category.assert_awaited_once_with(company.id, "earnings", limit=50)

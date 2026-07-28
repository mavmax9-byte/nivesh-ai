"""Repository tests against a real PostgreSQL test database."""

from datetime import UTC, datetime

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.news_intelligence.repository import NewsArticleRepository

_CHECKSUM_A = "a" * 64
_CHECKSUM_B = "b" * 64


async def _make_company(db_session, symbol: str = "TCS"):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    exchange = await exchange_repository.get_or_create_by_code("NSE")
    return await company_repository.upsert(
        symbol=symbol,
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )


def _article_data(company_id, **overrides) -> dict:
    defaults = dict(
        company_id=company_id,
        title="India's TCS rises after quarterly revenue beat",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 10, 3, 56, 27, tzinfo=UTC),
        url="https://sg.finance.yahoo.com/news/indias-tcs-rises-quarterly-revenue.html",
        summary="TCS shares rose after reporting quarterly revenue ahead of estimates.",
        full_content=None,
        language="en",
        category="markets",
        provider="yfinance-dev",
        checksum=_CHECKSUM_A,
    )
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_create_article_persists_and_commits(db_session):
    company = await _make_company(db_session)
    repository = NewsArticleRepository(db_session)

    article = await repository.create_article(_article_data(company.id))
    await repository.commit()

    fetched = await repository.get_by_checksum(_CHECKSUM_A)
    assert fetched is not None
    assert fetched.id == article.id
    assert fetched.category == "markets"


@pytest.mark.asyncio
async def test_get_by_checksum_returns_none_when_absent(db_session):
    repository = NewsArticleRepository(db_session)
    assert await repository.get_by_checksum(_CHECKSUM_B) is None


@pytest.mark.asyncio
async def test_checksum_uniqueness_is_enforced(db_session):
    company = await _make_company(db_session)
    repository = NewsArticleRepository(db_session)
    await repository.create_article(_article_data(company.id))
    await repository.commit()

    with pytest.raises(Exception):  # noqa: B017, PT011 -- IntegrityError from asyncpg/SQLAlchemy
        await repository.create_article(_article_data(company.id, title="A different headline"))
        await repository.commit()


@pytest.mark.asyncio
async def test_list_by_company_orders_newest_published_first(db_session):
    company = await _make_company(db_session)
    repository = NewsArticleRepository(db_session)

    older = await repository.create_article(
        _article_data(
            company.id,
            checksum=_CHECKSUM_B,
            published_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )
    await repository.commit()
    newer = await repository.create_article(_article_data(company.id))
    await repository.commit()

    articles = await repository.list_by_company(company.id)
    assert [a.id for a in articles] == [newer.id, older.id]


@pytest.mark.asyncio
async def test_list_by_category_filters_correctly(db_session):
    company = await _make_company(db_session)
    repository = NewsArticleRepository(db_session)

    markets_article = await repository.create_article(_article_data(company.id))
    await repository.commit()
    await repository.create_article(
        _article_data(company.id, checksum=_CHECKSUM_B, category="earnings")
    )
    await repository.commit()

    matches = await repository.list_by_category(company.id, "markets")
    assert [a.id for a in matches] == [markets_article.id]

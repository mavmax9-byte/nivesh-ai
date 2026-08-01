"""Repository tests against a real PostgreSQL test database with pgvector."""

from uuid import uuid4

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.knowledge_layer.repository import KnowledgeEmbeddingRepository

_DIMENSIONS = 1536


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


def _vector(*, first: float = 1.0, second: float = 0.0) -> list[float]:
    vector = [0.0] * _DIMENSIONS
    vector[0] = first
    vector[1] = second
    return vector


def _row(
    company_id, source_type, source_id, *, title="Title", text="Some text", vector=None
) -> dict:
    return {
        "company_id": company_id,
        "source_type": source_type,
        "source_table": "companies",
        "source_id": source_id,
        "title": title,
        "content_text": text,
        "content_checksum": "a" * 64,
        "embedding": vector or _vector(),
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": _DIMENSIONS,
    }


@pytest.mark.asyncio
async def test_bulk_upsert_persists_rows(db_session):
    company = await _make_company(db_session)
    repository = KnowledgeEmbeddingRepository(db_session)

    count = await repository.bulk_upsert([_row(company.id, "company_profile", company.id)])

    assert count == 1
    rows = await repository.list_by_company(company.id)
    assert len(rows) == 1
    assert rows[0].source_type == "company_profile"


@pytest.mark.asyncio
async def test_bulk_upsert_is_idempotent_on_conflict(db_session):
    company = await _make_company(db_session)
    repository = KnowledgeEmbeddingRepository(db_session)
    source_id = uuid4()

    await repository.bulk_upsert([_row(company.id, "news_article", source_id, text="Original")])
    await repository.bulk_upsert([_row(company.id, "news_article", source_id, text="Updated")])

    rows = await repository.list_by_company(company.id)
    assert len(rows) == 1
    assert rows[0].content_text == "Updated"


@pytest.mark.asyncio
async def test_bulk_upsert_advances_updated_at_on_conflict(db_session):
    """`updated_at` has `onupdate=func.now()` on the model, but that's an
    ORM-level hook that never fires for this Core-level
    `on_conflict_do_update` statement -- see repository.py's comment (same
    bug class found and fixed across ai_agents/knowledge_layer/
    technical_intelligence during v1.2 live verification)."""
    company = await _make_company(db_session)
    repository = KnowledgeEmbeddingRepository(db_session)
    source_id = uuid4()

    await repository.bulk_upsert([_row(company.id, "news_article", source_id, text="Original")])
    first = (await repository.list_by_company(company.id))[0]
    first_updated_at, first_created_at = first.updated_at, first.created_at

    await repository.bulk_upsert([_row(company.id, "news_article", source_id, text="Updated")])
    # `bulk_upsert` writes via a raw Core statement, which the ORM's identity
    # map never observes -- without expiring, this second read would
    # silently return the same stale, already-loaded Python object. Expire
    # only `first` (not `expire_all`, which would also expire `company` and
    # trip a MissingGreenlet on the plain `company.id` access below).
    db_session.expire(first)
    second = (await repository.list_by_company(company.id))[0]

    assert second.updated_at > first_updated_at
    assert second.created_at == first_created_at


@pytest.mark.asyncio
async def test_get_checksums_by_company_returns_map(db_session):
    company = await _make_company(db_session)
    repository = KnowledgeEmbeddingRepository(db_session)
    source_id = uuid4()
    row = _row(company.id, "news_article", source_id)
    row["content_checksum"] = "b" * 64
    await repository.bulk_upsert([row])

    checksums = await repository.get_checksums_by_company(company.id)

    assert checksums[("news_article", source_id)] == "b" * 64


@pytest.mark.asyncio
async def test_search_similar_by_company_orders_by_cosine_distance(db_session):
    company = await _make_company(db_session)
    repository = KnowledgeEmbeddingRepository(db_session)

    identical_id, orthogonal_id, opposite_id = uuid4(), uuid4(), uuid4()
    await repository.bulk_upsert(
        [
            _row(company.id, "news_article", identical_id, title="Identical", vector=_vector()),
            _row(
                company.id,
                "news_article",
                opposite_id,
                title="Opposite",
                vector=_vector(first=-1.0),
            ),
            _row(
                company.id,
                "news_article",
                orthogonal_id,
                title="Orthogonal",
                vector=_vector(first=0.0, second=1.0),
            ),
        ]
    )

    hits = await repository.search_similar_by_company(company.id, _vector(), limit=3)

    ordered_titles = [row.title for row, _distance in hits]
    assert ordered_titles == ["Identical", "Orthogonal", "Opposite"]
    assert hits[0][1] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_search_similar_by_company_is_scoped_per_company(db_session):
    company_a = await _make_company(db_session, symbol="TCS")
    company_b = await _make_company(db_session, symbol="INFY")
    repository = KnowledgeEmbeddingRepository(db_session)

    await repository.bulk_upsert(
        [_row(company_b.id, "news_article", uuid4(), title="Belongs to INFY")]
    )

    hits = await repository.search_similar_by_company(company_a.id, _vector(), limit=10)

    assert hits == []


@pytest.mark.asyncio
async def test_list_by_company_returns_only_that_companys_rows(db_session):
    company_a = await _make_company(db_session, symbol="TCS")
    company_b = await _make_company(db_session, symbol="INFY")
    repository = KnowledgeEmbeddingRepository(db_session)

    await repository.bulk_upsert([_row(company_a.id, "news_article", uuid4(), title="A-1")])
    await repository.bulk_upsert([_row(company_a.id, "news_article", uuid4(), title="A-2")])
    await repository.bulk_upsert([_row(company_b.id, "news_article", uuid4(), title="B-1")])

    rows = await repository.list_by_company(company_a.id)

    assert {row.title for row in rows} == {"A-1", "A-2"}

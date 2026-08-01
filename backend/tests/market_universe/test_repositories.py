"""Repository tests against a real PostgreSQL test database."""

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.market_universe.models import STATUS_FAILED, STATUS_PENDING, STATUS_READY
from nivesh.market_universe.repository import UniverseConstituentRepository

INDEX = "NIFTY50"


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


@pytest.mark.asyncio
async def test_seed_creates_rows_for_new_symbols(db_session):
    repository = UniverseConstituentRepository(db_session)

    seeded = await repository.seed(INDEX, ("TCS", "INFY"))

    assert seeded == 2
    tracked = await repository.list_by_index(INDEX)
    assert {c.symbol for c in tracked} == {"TCS", "INFY"}
    assert all(c.ingestion_status == STATUS_PENDING for c in tracked)


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_leaves_existing_rows_untouched(db_session):
    repository = UniverseConstituentRepository(db_session)
    await repository.seed(INDEX, ("TCS",))
    constituent = await repository.get_by_symbol(INDEX, "TCS")
    await repository.mark_ingesting(constituent)

    seeded_again = await repository.seed(INDEX, ("TCS", "INFY"))

    assert seeded_again == 1  # only INFY is new
    still_ingesting = await repository.get_by_symbol(INDEX, "TCS")
    assert still_ingesting.ingestion_status == "ingesting"


@pytest.mark.asyncio
async def test_mark_ready_sets_company_id_and_status(db_session):
    repository = UniverseConstituentRepository(db_session)
    await repository.seed(INDEX, ("TCS",))
    constituent = await repository.get_by_symbol(INDEX, "TCS")
    company = await _make_company(db_session)

    await repository.mark_ready(constituent, company_id=company.id)

    fetched = await repository.get_by_symbol(INDEX, "TCS")
    assert fetched.ingestion_status == STATUS_READY
    assert fetched.company_id == company.id
    assert fetched.last_ingested_at is not None


@pytest.mark.asyncio
async def test_mark_failed_records_truncated_reason(db_session):
    repository = UniverseConstituentRepository(db_session)
    await repository.seed(INDEX, ("TCS",))
    constituent = await repository.get_by_symbol(INDEX, "TCS")

    await repository.mark_failed(constituent, reason="provider timed out")

    fetched = await repository.get_by_symbol(INDEX, "TCS")
    assert fetched.ingestion_status == STATUS_FAILED
    assert fetched.ingestion_error == "provider timed out"


@pytest.mark.asyncio
async def test_get_screening_scores_only_returns_scored_companies(db_session):
    repository = UniverseConstituentRepository(db_session)
    await repository.seed(INDEX, ("TCS", "INFY"))
    tcs = await repository.get_by_symbol(INDEX, "TCS")
    infy = await repository.get_by_symbol(INDEX, "INFY")
    tcs_company = await _make_company(db_session, "TCS")
    infy_company = await _make_company(db_session, "INFY")
    await repository.mark_ready(tcs, company_id=tcs_company.id)
    await repository.mark_ready(infy, company_id=infy_company.id)
    await repository.update_screening(tcs, score=0.8, is_screened_in=True)
    # INFY intentionally left unscored.

    scores = await repository.get_screening_scores([tcs_company.id, infy_company.id])

    assert scores == {tcs_company.id: 0.8}


@pytest.mark.asyncio
async def test_get_screening_scores_empty_input_returns_empty(db_session):
    repository = UniverseConstituentRepository(db_session)
    assert await repository.get_screening_scores([]) == {}


@pytest.mark.asyncio
async def test_get_by_symbol_returns_none_for_unknown(db_session):
    repository = UniverseConstituentRepository(db_session)
    assert await repository.get_by_symbol(INDEX, "NOPE") is None


@pytest.mark.asyncio
async def test_list_by_index_filters_by_status(db_session):
    repository = UniverseConstituentRepository(db_session)
    await repository.seed(INDEX, ("TCS", "INFY"))
    tcs = await repository.get_by_symbol(INDEX, "TCS")
    await repository.mark_ingesting(tcs)

    pending_only = await repository.list_by_index(INDEX, statuses={STATUS_PENDING})

    assert [c.symbol for c in pending_only] == ["INFY"]

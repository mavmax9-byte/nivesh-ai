"""Repository tests against a real PostgreSQL test database."""

from datetime import UTC, date, datetime

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.technical_intelligence.repository import TechnicalIndicatorRepository


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


def _row(company_id, trading_date, indicator_name, value, parameters=None) -> dict:
    return {
        "company_id": company_id,
        "trading_date": trading_date,
        "indicator_name": indicator_name,
        "indicator_parameters": parameters or {"period": 20},
        "indicator_value": value,
        "calculation_timestamp": datetime.now(UTC),
    }


@pytest.mark.asyncio
async def test_bulk_upsert_persists_rows(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)

    count = await repository.bulk_upsert(
        [
            _row(company.id, date(2026, 1, 1), "sma_20", 100.0),
            _row(company.id, date(2026, 1, 2), "sma_20", 101.0),
        ]
    )

    assert count == 2
    history = await repository.get_history_by_indicator(company.id, "sma_20")
    assert len(history) == 2


@pytest.mark.asyncio
async def test_bulk_upsert_is_idempotent_on_conflict(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)

    await repository.bulk_upsert([_row(company.id, date(2026, 1, 1), "sma_20", 100.0)])
    await repository.bulk_upsert([_row(company.id, date(2026, 1, 1), "sma_20", 105.5)])

    history = await repository.get_history_by_indicator(company.id, "sma_20")
    assert len(history) == 1
    assert float(history[0].indicator_value) == pytest.approx(105.5)


@pytest.mark.asyncio
async def test_bulk_upsert_advances_updated_at_on_conflict(db_session):
    """`updated_at` has `onupdate=func.now()` on the model, but that's an
    ORM-level hook that never fires for this Core-level
    `on_conflict_do_update` statement -- see repository.py's comment (same
    bug class found and fixed across ai_agents/knowledge_layer/
    technical_intelligence during v1.2 live verification)."""
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)

    await repository.bulk_upsert([_row(company.id, date(2026, 1, 1), "sma_20", 100.0)])
    first = (await repository.get_history_by_indicator(company.id, "sma_20"))[0]
    first_updated_at, first_created_at = first.updated_at, first.created_at

    await repository.bulk_upsert([_row(company.id, date(2026, 1, 1), "sma_20", 105.5)])
    # `bulk_upsert` writes via a raw Core statement, which the ORM's identity
    # map never observes -- without expiring, this second read would
    # silently return the same stale, already-loaded Python object. Expire
    # only `first` (not `expire_all`, which would also expire `company` and
    # trip a MissingGreenlet on the plain `company.id` access below).
    db_session.expire(first)
    second = (await repository.get_history_by_indicator(company.id, "sma_20"))[0]

    assert second.updated_at > first_updated_at
    assert second.created_at == first_created_at


@pytest.mark.asyncio
async def test_get_last_indicator_value_returns_most_recent(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(company.id, date(2026, 1, 1), "obv", 1000.0, {}),
            _row(company.id, date(2026, 1, 3), "obv", 3000.0, {}),
            _row(company.id, date(2026, 1, 2), "obv", 2000.0, {}),
        ]
    )

    latest = await repository.get_last_indicator_value(company.id, "obv")

    assert latest is not None
    assert latest.trading_date == date(2026, 1, 3)
    assert float(latest.indicator_value) == pytest.approx(3000.0)


@pytest.mark.asyncio
async def test_get_last_indicator_value_returns_none_when_absent(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)
    assert await repository.get_last_indicator_value(company.id, "obv") is None


@pytest.mark.asyncio
async def test_get_latest_snapshot_returns_one_row_per_indicator(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(company.id, date(2026, 1, 1), "sma_20", 100.0),
            _row(company.id, date(2026, 1, 2), "sma_20", 101.0),
            _row(company.id, date(2026, 1, 1), "ema_20", 99.0),
            _row(company.id, date(2026, 1, 2), "ema_20", 99.5),
        ]
    )

    snapshot = await repository.get_latest_snapshot(company.id)

    assert len(snapshot) == 2
    by_name = {row.indicator_name: row for row in snapshot}
    assert by_name["sma_20"].trading_date == date(2026, 1, 2)
    assert by_name["ema_20"].trading_date == date(2026, 1, 2)


@pytest.mark.asyncio
async def test_get_history_orders_newest_first(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(company.id, date(2026, 1, 1), "sma_20", 100.0),
            _row(company.id, date(2026, 1, 3), "sma_20", 102.0),
            _row(company.id, date(2026, 1, 2), "sma_20", 101.0),
        ]
    )

    history = await repository.get_history(company.id)

    assert [row.trading_date for row in history] == [
        date(2026, 1, 3),
        date(2026, 1, 2),
        date(2026, 1, 1),
    ]


@pytest.mark.asyncio
async def test_get_history_by_indicator_filters_correctly(db_session):
    company = await _make_company(db_session)
    repository = TechnicalIndicatorRepository(db_session)
    await repository.bulk_upsert(
        [
            _row(company.id, date(2026, 1, 1), "sma_20", 100.0),
            _row(company.id, date(2026, 1, 1), "ema_20", 99.0),
        ]
    )

    sma_only = await repository.get_history_by_indicator(company.id, "sma_20")

    assert len(sma_only) == 1
    assert sma_only[0].indicator_name == "sma_20"

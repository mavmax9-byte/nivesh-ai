"""Repository tests against a real PostgreSQL test database.

Exercises the full aggregate-root write sequence (version -> snapshot ->
sources -> timeline -> finalize) and the read paths the API depends on.
"""

from datetime import date
from decimal import Decimal

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.research.models import (
    SOURCE_TYPE_CORPORATE_ACTION,
    SOURCE_TYPE_MARKET_DATA,
    TRIGGERED_BY_MARKET_DATA_SYNC,
)
from nivesh.research.repository import ResearchDossierRepository


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
async def test_get_or_create_dossier_is_idempotent(db_session):
    company = await _make_company(db_session)
    repository = ResearchDossierRepository(db_session)

    first = await repository.get_or_create_dossier(company.id)
    second = await repository.get_or_create_dossier(company.id)

    assert first.id == second.id
    assert first.current_version_number == 0
    assert first.last_market_data_watermark is None


@pytest.mark.asyncio
async def test_full_version_write_sequence_is_queryable(db_session):
    company = await _make_company(db_session)
    repository = ResearchDossierRepository(db_session)
    dossier = await repository.get_or_create_dossier(company.id)

    version = await repository.create_version(
        dossier_id=dossier.id,
        version_number=1,
        triggered_by=TRIGGERED_BY_MARKET_DATA_SYNC,
        change_summary="Initial research version: 10 price bar(s), 0 corporate action(s).",
    )
    await repository.create_snapshot(
        version_id=version.id,
        company_id=company.id,
        sector="Technology",
        industry="IT Services",
        latest_price=Decimal("3500.00"),
        latest_trade_date=date(2026, 1, 15),
        price_bar_count=10,
        price_history_start=date(2026, 1, 2),
        price_history_end=date(2026, 1, 15),
        corporate_action_count=0,
        latest_corporate_action_date=None,
    )
    await repository.bulk_create_sources(
        [
            {
                "dossier_id": dossier.id,
                "version_id": version.id,
                "source_type": SOURCE_TYPE_MARKET_DATA,
                "reference_table": "historical_ohlcv",
                "reference_id": None,
                "range_start": date(2026, 1, 2),
                "range_end": date(2026, 1, 15),
                "record_count": 10,
            }
        ]
    )
    await repository.create_timeline_event(
        dossier_id=dossier.id,
        company_id=company.id,
        event_type="version_created",
        description="Initial research version.",
        version_id=version.id,
    )
    await repository.finalize_version(
        dossier=dossier,
        version_number=1,
        watermark={
            "price_bar_count": 10,
            "latest_trade_date": "2026-01-15",
            "corporate_action_count": 0,
        },
    )

    refreshed_dossier = await repository.get_by_company_id(company.id)
    assert refreshed_dossier.current_version_number == 1
    assert refreshed_dossier.last_market_data_watermark["price_bar_count"] == 10
    assert refreshed_dossier.last_refreshed_at is not None

    latest = await repository.get_latest_version(dossier.id)
    assert latest.version_number == 1
    assert latest.snapshot is not None
    assert latest.snapshot.latest_price == Decimal("3500.00")

    timeline = await repository.get_recent_timeline(dossier.id)
    assert len(timeline) == 1
    assert timeline[0].event_type == "version_created"

    evidence_counts = await repository.get_evidence_counts(version.id)
    assert evidence_counts == {SOURCE_TYPE_MARKET_DATA: 10}


@pytest.mark.asyncio
async def test_version_history_orders_newest_first_and_paginates(db_session):
    company = await _make_company(db_session)
    repository = ResearchDossierRepository(db_session)
    dossier = await repository.get_or_create_dossier(company.id)

    for version_number in range(1, 4):
        await repository.create_version(
            dossier_id=dossier.id,
            version_number=version_number,
            triggered_by=TRIGGERED_BY_MARKET_DATA_SYNC,
            change_summary=f"Version {version_number}.",
        )
        await repository.finalize_version(
            dossier=dossier,
            version_number=version_number,
            watermark={
                "price_bar_count": version_number,
                "latest_trade_date": None,
                "corporate_action_count": 0,
            },
        )

    history = await repository.get_version_history(dossier.id, limit=2, offset=0)
    assert [v.version_number for v in history] == [3, 2]

    next_page = await repository.get_version_history(dossier.id, limit=2, offset=2)
    assert [v.version_number for v in next_page] == [1]


@pytest.mark.asyncio
async def test_evidence_counts_aggregate_multiple_source_rows(db_session):
    company = await _make_company(db_session)
    repository = ResearchDossierRepository(db_session)
    dossier = await repository.get_or_create_dossier(company.id)
    version = await repository.create_version(
        dossier_id=dossier.id,
        version_number=1,
        triggered_by=TRIGGERED_BY_MARKET_DATA_SYNC,
        change_summary="Initial.",
    )

    await repository.bulk_create_sources(
        [
            {
                "dossier_id": dossier.id,
                "version_id": version.id,
                "source_type": SOURCE_TYPE_MARKET_DATA,
                "reference_table": "historical_ohlcv",
                "reference_id": None,
                "range_start": date(2026, 1, 1),
                "range_end": date(2026, 1, 31),
                "record_count": 21,
            },
            {
                "dossier_id": dossier.id,
                "version_id": version.id,
                "source_type": SOURCE_TYPE_CORPORATE_ACTION,
                "reference_table": "corporate_actions",
                "reference_id": None,
                "range_start": date(2026, 1, 5),
                "range_end": date(2026, 1, 5),
                "record_count": 1,
            },
            {
                "dossier_id": dossier.id,
                "version_id": version.id,
                "source_type": SOURCE_TYPE_CORPORATE_ACTION,
                "reference_table": "corporate_actions",
                "reference_id": None,
                "range_start": date(2026, 1, 20),
                "range_end": date(2026, 1, 20),
                "record_count": 1,
            },
        ]
    )
    await db_session.commit()

    counts = await repository.get_evidence_counts(version.id)
    assert counts == {SOURCE_TYPE_MARKET_DATA: 21, SOURCE_TYPE_CORPORATE_ACTION: 2}


@pytest.mark.asyncio
async def test_bulk_create_sources_with_empty_list_is_a_no_op(db_session):
    repository = ResearchDossierRepository(db_session)
    assert await repository.bulk_create_sources([]) == 0

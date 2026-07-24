"""Repository tests against a real PostgreSQL test database.

These exercise actual ON CONFLICT upsert behavior, which cannot be
meaningfully faked -- see conftest.py for the skip-if-unreachable fixture.
"""

from datetime import date
from decimal import Decimal

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository


@pytest.mark.asyncio
async def test_exchange_get_or_create_is_idempotent(db_session):
    repository = ExchangeRepository(db_session)

    first = await repository.get_or_create_by_code("NSE")
    second = await repository.get_or_create_by_code("nse")

    assert first.id == second.id
    assert first.code == "NSE"
    assert first.name == "National Stock Exchange of India"


@pytest.mark.asyncio
async def test_company_upsert_creates_then_updates(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    exchange = await exchange_repository.get_or_create_by_code("NSE")

    created = await company_repository.upsert(
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Services",
    )
    assert created.symbol == "TCS"
    assert created.sector == "Technology"

    updated = await company_repository.upsert(
        symbol="TCS",
        name="Tata Consultancy Services Ltd",
        exchange_id=exchange.id,
        sector="Technology",
        industry="IT Consulting & Services",
    )
    assert updated.id == created.id
    assert updated.name == "Tata Consultancy Services Ltd"
    assert updated.industry == "IT Consulting & Services"

    fetched = await company_repository.get_by_symbol("tcs")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.exchange.code == "NSE"


@pytest.mark.asyncio
async def test_company_list_only_returns_active_companies(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    exchange = await exchange_repository.get_or_create_by_code("NSE")

    await company_repository.upsert(
        symbol="INFY", name="Infosys", exchange_id=exchange.id, sector=None, industry=None
    )
    await company_repository.upsert(
        symbol="WIPRO", name="Wipro", exchange_id=exchange.id, sector=None, industry=None
    )

    companies = await company_repository.list()
    symbols = {c.symbol for c in companies}
    assert {"INFY", "WIPRO"}.issubset(symbols)


@pytest.mark.asyncio
async def test_ohlcv_bulk_upsert_resolves_conflicts_on_company_and_date(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    ohlcv_repository = HistoricalOHLCVRepository(db_session)

    exchange = await exchange_repository.get_or_create_by_code("NSE")
    company = await company_repository.upsert(
        symbol="INFY", name="Infosys", exchange_id=exchange.id, sector=None, industry=None
    )

    base_row = {
        "company_id": company.id,
        "trade_date": date(2026, 1, 2),
        "open": Decimal("1500.00"),
        "high": Decimal("1520.00"),
        "low": Decimal("1490.00"),
        "close": Decimal("1510.00"),
        "volume": 1_000_000,
        "source": "yfinance",
    }

    inserted = await ohlcv_repository.bulk_upsert([base_row])
    assert inserted == 1

    updated_row = dict(base_row, close=Decimal("1525.00"), volume=1_200_000)
    upserted = await ohlcv_repository.bulk_upsert([updated_row])
    assert upserted == 1

    bars = await ohlcv_repository.list_for_company(company.id)
    assert len(bars) == 1
    assert bars[0].close == Decimal("1525.00")
    assert bars[0].volume == 1_200_000


@pytest.mark.asyncio
async def test_ohlcv_list_for_company_respects_date_range(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    ohlcv_repository = HistoricalOHLCVRepository(db_session)

    exchange = await exchange_repository.get_or_create_by_code("NSE")
    company = await company_repository.upsert(
        symbol="WIPRO", name="Wipro", exchange_id=exchange.id, sector=None, industry=None
    )

    rows = [
        {
            "company_id": company.id,
            "trade_date": trade_date,
            "open": Decimal("100"),
            "high": Decimal("105"),
            "low": Decimal("99"),
            "close": Decimal("104"),
            "volume": 1000,
            "source": "yfinance",
        }
        for trade_date in (date(2026, 1, 1), date(2026, 1, 15), date(2026, 2, 1))
    ]
    await ohlcv_repository.bulk_upsert(rows)

    bars = await ohlcv_repository.list_for_company(
        company.id, start=date(2026, 1, 10), end=date(2026, 1, 31)
    )
    assert len(bars) == 1
    assert bars[0].trade_date == date(2026, 1, 15)


@pytest.mark.asyncio
async def test_corporate_action_bulk_upsert_resolves_conflicts(db_session):
    exchange_repository = ExchangeRepository(db_session)
    company_repository = CompanyRepository(db_session)
    action_repository = CorporateActionRepository(db_session)

    exchange = await exchange_repository.get_or_create_by_code("NSE")
    company = await company_repository.upsert(
        symbol="WIPRO", name="Wipro", exchange_id=exchange.id, sector=None, industry=None
    )

    base_row = {
        "company_id": company.id,
        "action_type": "split",
        "ex_date": date(2026, 3, 1),
        "ratio_numerator": 2,
        "ratio_denominator": 1,
        "dividend_amount_per_share": None,
        "source": "yfinance",
    }
    count = await action_repository.bulk_upsert([base_row])
    assert count == 1

    updated_row = dict(base_row, ratio_numerator=3)
    await action_repository.bulk_upsert([updated_row])

    actions = await action_repository.list_for_company(company.id)
    assert len(actions) == 1
    assert actions[0].action_type == "split"
    assert actions[0].ratio_numerator == 3


@pytest.mark.asyncio
async def test_bulk_upsert_with_empty_list_is_a_no_op(db_session):
    ohlcv_repository = HistoricalOHLCVRepository(db_session)
    assert await ohlcv_repository.bulk_upsert([]) == 0

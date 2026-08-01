"""Repository tests against a real PostgreSQL test database."""

import uuid

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.portfolio_planner.models import STATUS_FAILED, STATUS_GENERATING, STATUS_READY
from nivesh.portfolio_planner.repository import PlannedPortfolioRepository


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
async def test_create_generating_persists_a_new_portfolio(db_session):
    repository = PlannedPortfolioRepository(db_session)

    portfolio = await repository.create_generating(
        capital=100000.0, risk_profile="balanced", horizon="medium", sector_exclusions=["Energy"]
    )

    assert portfolio.id is not None
    assert portfolio.status == STATUS_GENERATING
    assert portfolio.capital == pytest.approx(100000.0)
    assert portfolio.sector_exclusions == ["Energy"]


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_unknown_id(db_session):
    repository = PlannedPortfolioRepository(db_session)
    result = await repository.get_by_id(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_add_holding_and_mark_ready_round_trip(db_session):
    company = await _make_company(db_session)
    repository = PlannedPortfolioRepository(db_session)
    portfolio = await repository.create_generating(
        capital=50000.0, risk_profile="growth", horizon="long", sector_exclusions=[]
    )

    await repository.add_holding(
        portfolio.id,
        {
            "company_id": company.id,
            "symbol": company.symbol,
            "company_name": company.name,
            "sector": company.sector,
            "allocated_amount": 10000.0,
            "allocated_weight": 0.2,
            "rank_score": 0.75,
            "confidence_score": 0.7,
            "evidence_sufficiency": "sufficient",
            "thesis": "Strong fundamentals.",
            "weight_rationale": "Allocated 20% based on composite score.",
            "top_citation_title": "Quarterly statement",
            "top_citation_source_type": "financial_statement",
        },
    )

    ready = await repository.mark_ready(
        portfolio,
        summary="One holding in Technology.",
        caveats=["Small universe."],
        unallocated_amount=40000.0,
        confidence_score=0.7,
        evidence_sufficiency="sufficient",
        universe_size=1,
    )

    assert ready.status == STATUS_READY
    assert ready.unallocated_amount == pytest.approx(40000.0)

    fetched = await repository.get_by_id(portfolio.id)
    assert fetched is not None
    assert len(fetched.holdings) == 1
    assert fetched.holdings[0].symbol == "TCS"
    assert fetched.holdings[0].allocated_amount == pytest.approx(10000.0)


@pytest.mark.asyncio
async def test_mark_failed_records_reason(db_session):
    repository = PlannedPortfolioRepository(db_session)
    portfolio = await repository.create_generating(
        capital=1000.0, risk_profile="conservative", horizon="short", sector_exclusions=[]
    )

    failed = await repository.mark_failed(portfolio, reason="No eligible companies.")

    assert failed.status == STATUS_FAILED
    assert failed.failure_reason == "No eligible companies."

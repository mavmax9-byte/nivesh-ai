"""Repository tests against a real PostgreSQL test database.

Exercises the aggregate-root write sequence (filing -> version -> commit)
and the lookup paths the service and API depend on.
"""

from datetime import date

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.corporate_filings.models import (
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_QUARTERLY_RESULTS,
)
from nivesh.corporate_filings.repository import (
    CorporateFilingRepository,
    FilingCategoryRepository,
    FilingSourceRepository,
)

_CHECKSUM_A = "a" * 64
_CHECKSUM_B = "b" * 64
_CHECKSUM_C = "c" * 64


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


def _filing_data(company_id, category_id, source_id, **overrides) -> dict:
    defaults = dict(
        company_id=company_id,
        category_id=category_id,
        source_id=source_id,
        exchange="NSE",
        filing_type=FILING_TYPE_QUARTERLY_RESULTS,
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum=_CHECKSUM_A,
        language="en",
        document_size=None,
        version_number=1,
    )
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_filing_category_get_or_create_is_idempotent(db_session):
    repository = FilingCategoryRepository(db_session)

    first = await repository.get_or_create_by_code("financial_results", "Financial Results")
    second = await repository.get_or_create_by_code("financial_results", "Financial Results")

    assert first.id == second.id
    assert first.name == "Financial Results"


@pytest.mark.asyncio
async def test_filing_source_get_or_create_is_idempotent(db_session):
    repository = FilingSourceRepository(db_session)

    first = await repository.get_or_create_by_code("yfinance-dev", "Development Provider")
    second = await repository.get_or_create_by_code("yfinance-dev", "Development Provider")

    assert first.id == second.id


@pytest.mark.asyncio
async def test_create_filing_persists_full_aggregate(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    filing = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.create_filing_version(
        {
            "filing_id": filing.id,
            "company_id": company.id,
            "version_number": 1,
            "title": filing.title,
            "filing_date": filing.filing_date,
            "source_url": filing.source_url,
            "checksum": filing.checksum,
            "document_size": filing.document_size,
        }
    )
    filing = await repository.commit_filing(filing)

    assert filing.version_number == 1
    assert filing.category.code == "financial_results"
    assert filing.source.code == "yfinance-dev"
    assert len(filing.versions) == 1
    assert filing.versions[0].checksum == _CHECKSUM_A


@pytest.mark.asyncio
async def test_get_by_identity_returns_current_state(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    created = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.commit_filing(created)

    fetched = await repository.get_by_identity(
        company.id, FILING_TYPE_QUARTERLY_RESULTS, "Q2FY2026"
    )
    assert fetched is not None
    assert fetched.id == created.id

    missing = await repository.get_by_identity(
        company.id, FILING_TYPE_QUARTERLY_RESULTS, "Q3FY2026"
    )
    assert missing is None


@pytest.mark.asyncio
async def test_get_by_checksum_finds_the_owning_filing(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)
    created = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.commit_filing(created)

    found = await repository.get_by_checksum(_CHECKSUM_A)
    assert found is not None
    assert found.id == created.id

    assert await repository.get_by_checksum(_CHECKSUM_B) is None


@pytest.mark.asyncio
async def test_update_filing_bumps_version_and_records_history(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    filing = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.create_filing_version(
        {
            "filing_id": filing.id,
            "company_id": company.id,
            "version_number": 1,
            "title": filing.title,
            "filing_date": filing.filing_date,
            "source_url": filing.source_url,
            "checksum": filing.checksum,
            "document_size": filing.document_size,
        }
    )
    filing = await repository.commit_filing(filing)

    updated = await repository.update_filing(
        filing,
        {"checksum": _CHECKSUM_B, "version_number": 2, "title": "TCS Quarterly Results (revised)"},
    )
    await repository.create_filing_version(
        {
            "filing_id": updated.id,
            "company_id": company.id,
            "version_number": 2,
            "title": updated.title,
            "filing_date": updated.filing_date,
            "source_url": updated.source_url,
            "checksum": updated.checksum,
            "document_size": updated.document_size,
        }
    )
    updated = await repository.commit_filing(updated)

    assert updated.id == filing.id
    assert updated.version_number == 2
    assert updated.checksum == _CHECKSUM_B

    history = await repository.get_version_history_for_company(company.id)
    assert [v.version_number for v in history] == [2, 1]


@pytest.mark.asyncio
async def test_list_by_filing_types_filters_correctly(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    quarterly = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.commit_filing(quarterly)

    annual = await repository.create_filing(
        _filing_data(
            company.id,
            category.id,
            source.id,
            filing_type=FILING_TYPE_ANNUAL_REPORT,
            reporting_period="FY2026",
            filing_date=date(2026, 3, 31),
            checksum=_CHECKSUM_B,
        )
    )
    await repository.commit_filing(annual)

    quarterly_results = await repository.list_by_filing_types(
        company.id, {FILING_TYPE_QUARTERLY_RESULTS}
    )
    assert [f.id for f in quarterly_results] == [quarterly.id]

    annual_results = await repository.list_by_filing_types(company.id, {FILING_TYPE_ANNUAL_REPORT})
    assert [f.id for f in annual_results] == [annual.id]


@pytest.mark.asyncio
async def test_list_by_category_code_filters_correctly(db_session):
    company = await _make_company(db_session)
    financial_results = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    governance = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "governance", "Governance"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    in_results = await repository.create_filing(
        _filing_data(company.id, financial_results.id, source.id)
    )
    await repository.commit_filing(in_results)

    in_governance = await repository.create_filing(
        _filing_data(
            company.id,
            governance.id,
            source.id,
            filing_type="board_meeting",
            reporting_period="FY2026",
            filing_date=date(2026, 6, 1),
            checksum=_CHECKSUM_B,
        )
    )
    await repository.commit_filing(in_governance)

    matches = await repository.list_by_category_code(company.id, "governance")
    assert [f.id for f in matches] == [in_governance.id]


@pytest.mark.asyncio
async def test_list_by_reporting_period_and_date_range(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    q2 = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.commit_filing(q2)

    q3 = await repository.create_filing(
        _filing_data(
            company.id,
            category.id,
            source.id,
            reporting_period="Q3FY2026",
            filing_date=date(2027, 1, 15),
            checksum=_CHECKSUM_C,
        )
    )
    await repository.commit_filing(q3)

    by_period = await repository.list_by_reporting_period(company.id, "Q2FY2026")
    assert [f.id for f in by_period] == [q2.id]

    by_range = await repository.list_by_date_range(
        company.id, start=date(2026, 9, 1), end=date(2026, 11, 1)
    )
    assert [f.id for f in by_range] == [q2.id]


@pytest.mark.asyncio
async def test_list_by_company_orders_newest_filing_date_first(db_session):
    company = await _make_company(db_session)
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    repository = CorporateFilingRepository(db_session)

    older = await repository.create_filing(
        _filing_data(
            company.id,
            category.id,
            source.id,
            reporting_period="Q1FY2026",
            filing_date=date(2026, 7, 15),
            checksum=_CHECKSUM_B,
        )
    )
    await repository.commit_filing(older)

    newer = await repository.create_filing(_filing_data(company.id, category.id, source.id))
    await repository.commit_filing(newer)

    filings = await repository.list_by_company(company.id)
    assert [f.id for f in filings] == [newer.id, older.id]

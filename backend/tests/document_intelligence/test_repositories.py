"""Repository tests against a real PostgreSQL test database.

Exercises the aggregate-root write sequence (extraction -> sections ->
commit) and the lookup paths the service and API depend on, mirroring
corporate_filings/financials' test_repositories.py structure.
"""

from datetime import date

import pytest

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.corporate_filings.models import FILING_TYPE_QUARTERLY_RESULTS
from nivesh.corporate_filings.repository import (
    CorporateFilingRepository,
    FilingCategoryRepository,
    FilingSourceRepository,
)
from nivesh.document_intelligence.models import EXTRACTION_STATUS_COMPLETED
from nivesh.document_intelligence.repository import DocumentExtractionRepository

_CHECKSUM = "a" * 64


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


async def _make_filing_version(db_session, company, **overrides):
    category = await FilingCategoryRepository(db_session).get_or_create_by_code(
        "financial_results", "Financial Results"
    )
    source = await FilingSourceRepository(db_session).get_or_create_by_code(
        "yfinance-dev", "Development Provider"
    )
    filing_repository = CorporateFilingRepository(db_session)

    filing_data = dict(
        company_id=company.id,
        category_id=category.id,
        source_id=source.id,
        exchange="NSE",
        filing_type=FILING_TYPE_QUARTERLY_RESULTS,
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum=_CHECKSUM,
        language="en",
        document_size=None,
        version_number=1,
    )
    filing_data.update(overrides)

    filing = await filing_repository.create_filing(filing_data)
    filing_version = await filing_repository.create_filing_version(
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
    await filing_repository.commit_filing(filing)
    return filing_version


def _extraction_data(filing_version_id, company_id, **overrides) -> dict:
    defaults = dict(
        filing_version_id=filing_version_id,
        company_id=company_id,
        extraction_status=EXTRACTION_STATUS_COMPLETED,
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="--- Page 1 ---\nANNUAL REPORT\nBody text.",
        page_count=1,
        section_count=1,
    )
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_create_extraction_persists_full_aggregate(db_session):
    company = await _make_company(db_session)
    filing_version = await _make_filing_version(db_session, company)
    repository = DocumentExtractionRepository(db_session)

    extraction = await repository.create_extraction(_extraction_data(filing_version.id, company.id))
    await repository.create_sections(
        extraction.id,
        [
            {
                "sequence": 0,
                "heading": "ANNUAL REPORT",
                "level": 1,
                "page_number": 1,
                "content": "Body text.",
            }
        ],
    )
    extraction = await repository.commit_extraction(extraction)

    assert extraction.extraction_status == EXTRACTION_STATUS_COMPLETED
    assert len(extraction.sections) == 1
    assert extraction.sections[0].heading == "ANNUAL REPORT"
    assert extraction.sections[0].sequence == 0


@pytest.mark.asyncio
async def test_get_by_filing_version_returns_none_when_absent(db_session):
    company = await _make_company(db_session)
    filing_version = await _make_filing_version(db_session, company)
    repository = DocumentExtractionRepository(db_session)

    assert await repository.get_by_filing_version(filing_version.id) is None


@pytest.mark.asyncio
async def test_get_by_filing_version_returns_extraction_with_sections(db_session):
    company = await _make_company(db_session)
    filing_version = await _make_filing_version(db_session, company)
    repository = DocumentExtractionRepository(db_session)

    created = await repository.create_extraction(_extraction_data(filing_version.id, company.id))
    await repository.create_sections(
        created.id,
        [{"sequence": 0, "heading": "H", "level": 1, "page_number": 1, "content": "c"}],
    )
    await repository.commit_extraction(created)

    fetched = await repository.get_by_filing_version(filing_version.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert len(fetched.sections) == 1


@pytest.mark.asyncio
async def test_list_by_company_orders_newest_first(db_session):
    company = await _make_company(db_session)
    first_version = await _make_filing_version(db_session, company)
    repository = DocumentExtractionRepository(db_session)

    older = await repository.create_extraction(_extraction_data(first_version.id, company.id))
    await repository.commit_extraction(older)

    second_version = await _make_filing_version(
        db_session,
        company,
        reporting_period="Q3FY2026",
        filing_date=date(2027, 1, 15),
        checksum="b" * 64,
    )
    newer = await repository.create_extraction(_extraction_data(second_version.id, company.id))
    await repository.commit_extraction(newer)

    extractions = await repository.list_by_company(company.id)
    assert [e.id for e in extractions] == [newer.id, older.id]

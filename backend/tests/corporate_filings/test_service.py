from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.companies.models import Company, Exchange
from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import (
    ANNUAL_FILING_TYPES,
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_QUARTERLY_RESULTS,
    QUARTERLY_FILING_TYPES,
    CorporateFiling,
    FilingCategory,
    FilingSource,
)
from nivesh.corporate_filings.providers.base import ProviderFiling
from nivesh.corporate_filings.service import CorporateFilingsService
from nivesh.corporate_filings.validation import InvalidFilingDataError
from nivesh.research.models import CompanyResearchDossier, ResearchVersion

_CHECKSUM_A = "a" * 64
_CHECKSUM_B = "b" * 64


def _company(symbol: str = "TCS") -> Company:
    exchange = Exchange(id=uuid4(), code="NSE", name="National Stock Exchange of India")
    company = Company(
        id=uuid4(), symbol=symbol, name="Tata Consultancy Services", exchange_id=exchange.id
    )
    company.exchange = exchange
    return company


def _provider_filing(**overrides) -> ProviderFiling:
    defaults: dict = dict(
        exchange="NSE",
        filing_type=FILING_TYPE_QUARTERLY_RESULTS,
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum=_CHECKSUM_A,
        language="en",
        document_size=None,
    )
    defaults.update(overrides)
    return ProviderFiling(**defaults)


def _stored_filing(*, checksum: str = _CHECKSUM_A, version_number: int = 1) -> CorporateFiling:
    filing = CorporateFiling(
        id=uuid4(),
        company_id=uuid4(),
        exchange="NSE",
        filing_type=FILING_TYPE_QUARTERLY_RESULTS,
        category_id=uuid4(),
        source_id=uuid4(),
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum=checksum,
        language="en",
        document_size=None,
        version_number=version_number,
    )
    return filing


def _make_service(
    company,
    *,
    existing_filing=None,
    checksum_owner=None,
    latest_research_version=None,
):
    provider = AsyncMock()

    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = company

    category_repository = AsyncMock()
    category_repository.get_or_create_by_code.side_effect = lambda code, name: FilingCategory(
        id=uuid4(), code=code, name=name
    )

    source_repository = AsyncMock()
    source_repository.get_or_create_by_code.return_value = FilingSource(
        id=uuid4(), code="yfinance-dev", name="Development Provider"
    )

    filing_repository = AsyncMock()
    filing_repository.get_by_identity.return_value = existing_filing
    filing_repository.get_by_checksum.return_value = checksum_owner
    filing_repository.create_filing.side_effect = lambda data: CorporateFiling(id=uuid4(), **data)
    filing_repository.update_filing.side_effect = lambda filing, data: _apply_update(filing, data)
    filing_repository.commit_filing.side_effect = lambda filing: filing

    dossier_repository = AsyncMock()
    dossier_repository.get_or_create_dossier.return_value = CompanyResearchDossier(
        id=uuid4(), company_id=company.id
    )
    dossier_repository.get_latest_version.return_value = latest_research_version

    service = CorporateFilingsService(
        provider=provider,
        company_repository=company_repository,
        category_repository=category_repository,
        source_repository=source_repository,
        filing_repository=filing_repository,
        dossier_repository=dossier_repository,
    )
    return service, provider, filing_repository, dossier_repository


def _apply_update(filing: CorporateFiling, data: dict) -> CorporateFiling:
    for field, value in data.items():
        setattr(filing, field, value)
    return filing


@pytest.mark.asyncio
async def test_sync_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None

    service = CorporateFilingsService(
        provider=AsyncMock(),
        company_repository=company_repository,
        category_repository=AsyncMock(),
        source_repository=AsyncMock(),
        filing_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.sync_company_filings("NOPE")


@pytest.mark.asyncio
async def test_sync_creates_new_filing_and_links_dossier():
    company = _company()
    version = ResearchVersion(id=uuid4(), dossier_id=uuid4(), version_number=1)
    service, provider, filing_repository, dossier_repository = _make_service(
        company, latest_research_version=version
    )
    provider.get_filings.return_value = [_provider_filing()]

    result = await service.sync_company_filings("TCS")

    assert result.filings_synced == 1
    assert result.filings_unchanged == 0

    filing_repository.create_filing.assert_awaited_once()
    (create_data,) = filing_repository.create_filing.await_args.args
    assert create_data["version_number"] == 1
    assert create_data["filing_type"] == FILING_TYPE_QUARTERLY_RESULTS
    assert create_data["checksum"] == _CHECKSUM_A

    filing_repository.create_filing_version.assert_awaited_once()
    (version_data,) = filing_repository.create_filing_version.await_args.args
    assert version_data["version_number"] == 1

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert len(source_rows) == 1
    assert source_rows[0]["source_type"] == "corporate_filing"
    assert source_rows[0]["version_id"] == version.id

    dossier_repository.create_timeline_event.assert_awaited_once()
    filing_repository.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_skips_unchanged_filing():
    company = _company()
    existing = _stored_filing(checksum=_CHECKSUM_A)
    service, provider, filing_repository, dossier_repository = _make_service(
        company, existing_filing=existing
    )
    provider.get_filings.return_value = [_provider_filing(checksum=_CHECKSUM_A)]

    result = await service.sync_company_filings("TCS")

    assert result.filings_synced == 0
    assert result.filings_unchanged == 1
    filing_repository.create_filing.assert_not_awaited()
    filing_repository.update_filing.assert_not_awaited()
    dossier_repository.get_or_create_dossier.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_creates_next_version_when_checksum_changes():
    company = _company()
    existing = _stored_filing(checksum=_CHECKSUM_A, version_number=1)
    service, provider, filing_repository, dossier_repository = _make_service(
        company, existing_filing=existing, latest_research_version=None
    )
    provider.get_filings.return_value = [_provider_filing(checksum=_CHECKSUM_B)]

    result = await service.sync_company_filings("TCS")

    assert result.filings_synced == 1
    filing_repository.update_filing.assert_awaited_once()
    _, update_data = filing_repository.update_filing.await_args.args
    assert update_data["version_number"] == 2
    assert update_data["checksum"] == _CHECKSUM_B


@pytest.mark.asyncio
async def test_sync_rejects_checksum_reused_by_a_different_filing():
    company = _company()
    other_filing = _stored_filing(checksum=_CHECKSUM_B)
    service, provider, filing_repository, _ = _make_service(company, checksum_owner=other_filing)
    provider.get_filings.return_value = [_provider_filing(checksum=_CHECKSUM_B)]

    with pytest.raises(InvalidFilingDataError):
        await service.sync_company_filings("TCS")

    filing_repository.create_filing.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_rejects_unknown_filing_type():
    company = _company()
    service, provider, filing_repository, _ = _make_service(company)
    provider.get_filings.return_value = [_provider_filing(filing_type="press_release")]

    with pytest.raises(InvalidFilingDataError):
        await service.sync_company_filings("TCS")

    filing_repository.create_filing.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_rejects_reporting_period_mismatched_with_filing_type():
    company = _company()
    service, provider, filing_repository, _ = _make_service(company)
    provider.get_filings.return_value = [_provider_filing(reporting_period="FY2026")]

    with pytest.raises(InvalidFilingDataError):
        await service.sync_company_filings("TCS")

    filing_repository.create_filing.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_rejects_invalid_source_url():
    company = _company()
    service, provider, filing_repository, _ = _make_service(company)
    provider.get_filings.return_value = [_provider_filing(source_url="not-a-url")]

    with pytest.raises(InvalidFilingDataError):
        await service.sync_company_filings("TCS")

    filing_repository.create_filing.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_rejects_malformed_checksum():
    company = _company()
    service, provider, filing_repository, _ = _make_service(company)
    provider.get_filings.return_value = [_provider_filing(checksum="too-short")]

    with pytest.raises(InvalidFilingDataError):
        await service.sync_company_filings("TCS")

    filing_repository.create_filing.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_does_not_attach_evidence_when_no_research_version_exists_yet():
    company = _company()
    service, provider, filing_repository, dossier_repository = _make_service(
        company, latest_research_version=None
    )
    provider.get_filings.return_value = [_provider_filing()]

    result = await service.sync_company_filings("TCS")

    assert result.filings_synced == 1
    dossier_repository.get_or_create_dossier.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()
    filing_repository.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_annual_filings_queries_annual_filing_types():
    company = _company()
    service, _, filing_repository, _ = _make_service(company)
    filing_repository.list_by_filing_types.return_value = []

    await service.get_annual_filings("TCS")

    filing_repository.list_by_filing_types.assert_awaited_once_with(
        company.id, ANNUAL_FILING_TYPES, limit=50
    )


@pytest.mark.asyncio
async def test_get_quarterly_filings_queries_quarterly_filing_types():
    company = _company()
    service, _, filing_repository, _ = _make_service(company)
    filing_repository.list_by_filing_types.return_value = []

    await service.get_quarterly_filings("TCS")

    filing_repository.list_by_filing_types.assert_awaited_once_with(
        company.id, QUARTERLY_FILING_TYPES, limit=50
    )


@pytest.mark.asyncio
async def test_get_filings_by_category_delegates_to_repository():
    company = _company()
    service, _, filing_repository, _ = _make_service(company)
    filing_repository.list_by_category_code.return_value = []

    await service.get_filings_by_category("TCS", "governance")

    filing_repository.list_by_category_code.assert_awaited_once_with(
        company.id, "governance", limit=50
    )


@pytest.mark.asyncio
async def test_get_filing_history_delegates_to_repository():
    company = _company()
    service, _, filing_repository, _ = _make_service(company)
    filing_repository.get_version_history_for_company.return_value = []

    await service.get_filing_history("TCS")

    filing_repository.get_version_history_for_company.assert_awaited_once_with(
        company.id, limit=50, offset=0
    )


@pytest.mark.asyncio
async def test_get_filings_raises_not_found_for_unknown_symbol():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = CorporateFilingsService(
        provider=AsyncMock(),
        company_repository=company_repository,
        category_repository=AsyncMock(),
        source_repository=AsyncMock(),
        filing_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.get_filings("NOPE")


def test_filing_type_constants_are_disjoint():
    assert ANNUAL_FILING_TYPES.isdisjoint(QUARTERLY_FILING_TYPES)
    assert FILING_TYPE_ANNUAL_REPORT in ANNUAL_FILING_TYPES
    assert FILING_TYPE_QUARTERLY_RESULTS in QUARTERLY_FILING_TYPES

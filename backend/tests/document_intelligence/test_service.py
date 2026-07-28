from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import (
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_BOARD_MEETING,
    FILING_TYPE_QUARTERLY_RESULTS,
    CorporateFiling,
    FilingVersion,
)
from nivesh.document_intelligence.models import EXTRACTION_STATUS_COMPLETED, DocumentExtraction
from nivesh.document_intelligence.providers.base import (
    ProviderExtractedPage,
    ProviderExtractionResult,
)
from nivesh.document_intelligence.service import DocumentIntelligenceService
from nivesh.document_intelligence.validation import (
    DuplicateExtractionError,
    InvalidDocumentExtractionError,
)
from nivesh.research.models import CompanyResearchDossier, ResearchVersion


def _filing(filing_type: str = FILING_TYPE_QUARTERLY_RESULTS) -> CorporateFiling:
    return CorporateFiling(
        id=uuid4(),
        company_id=uuid4(),
        exchange="NSE",
        filing_type=filing_type,
        category_id=uuid4(),
        source_id=uuid4(),
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://example.com/tcs-q2fy2026.pdf",
        checksum="a" * 64,
        language="en",
        document_size=None,
        version_number=1,
    )


def _filing_version(filing: CorporateFiling, **overrides) -> FilingVersion:
    defaults = dict(
        id=uuid4(),
        filing_id=filing.id,
        company_id=filing.company_id,
        version_number=1,
        title=filing.title,
        filing_date=filing.filing_date,
        source_url=filing.source_url,
        checksum=filing.checksum,
        document_size=filing.document_size,
    )
    defaults.update(overrides)
    version = FilingVersion(**defaults)
    version.filing = filing
    return version


def _provider_result(pages: list[str]) -> ProviderExtractionResult:
    return ProviderExtractionResult(
        extractor_name="pypdf",
        extractor_version="5.0.0",
        pages=[
            ProviderExtractedPage(page_number=index + 1, text=text)
            for index, text in enumerate(pages)
        ],
    )


def _make_service(
    *,
    filing_version: FilingVersion | None = None,
    existing_extraction: DocumentExtraction | None = None,
    latest_research_version: ResearchVersion | None = None,
):
    provider = AsyncMock()

    filing_repository = AsyncMock()
    filing_repository.get_version_by_id.return_value = filing_version

    company_repository = AsyncMock()

    extraction_repository = AsyncMock()
    extraction_repository.get_by_filing_version.return_value = existing_extraction
    extraction_repository.create_extraction.side_effect = lambda data: DocumentExtraction(
        id=uuid4(), **data
    )
    extraction_repository.commit_extraction.side_effect = lambda extraction: extraction

    dossier_repository = AsyncMock()
    company_id = filing_version.company_id if filing_version is not None else uuid4()
    dossier_repository.get_or_create_dossier.return_value = CompanyResearchDossier(
        id=uuid4(), company_id=company_id
    )
    dossier_repository.get_latest_version.return_value = latest_research_version

    service = DocumentIntelligenceService(
        provider=provider,
        filing_repository=filing_repository,
        company_repository=company_repository,
        extraction_repository=extraction_repository,
        dossier_repository=dossier_repository,
    )
    return service, provider, filing_repository, extraction_repository, dossier_repository


@pytest.mark.asyncio
async def test_extract_raises_not_found_for_unknown_filing_version():
    service, provider, _, _, _ = _make_service(filing_version=None)

    with pytest.raises(NotFoundError):
        await service.extract_filing_document(uuid4())

    provider.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_rejects_non_extractable_filing_type():
    filing_version = _filing_version(_filing(filing_type=FILING_TYPE_BOARD_MEETING))
    service, provider, _, extraction_repository, _ = _make_service(filing_version=filing_version)

    with pytest.raises(InvalidDocumentExtractionError):
        await service.extract_filing_document(filing_version.id)

    provider.extract.assert_not_awaited()
    extraction_repository.create_extraction.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_rejects_duplicate_extraction():
    filing_version = _filing_version(_filing())
    existing = DocumentExtraction(
        id=uuid4(),
        filing_version_id=filing_version.id,
        company_id=filing_version.company_id,
        extraction_status=EXTRACTION_STATUS_COMPLETED,
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="text",
        page_count=1,
        section_count=1,
    )
    service, provider, _, _, _ = _make_service(
        filing_version=filing_version, existing_extraction=existing
    )

    with pytest.raises(DuplicateExtractionError):
        await service.extract_filing_document(filing_version.id)

    provider.extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_persists_extraction_and_sections_and_links_dossier():
    filing_version = _filing_version(_filing(filing_type=FILING_TYPE_ANNUAL_REPORT))
    research_version = ResearchVersion(id=uuid4(), dossier_id=uuid4(), version_number=1)
    service, provider, _, extraction_repository, dossier_repository = _make_service(
        filing_version=filing_version, latest_research_version=research_version
    )
    provider.extract.return_value = _provider_result(["ANNUAL REPORT\nBody text goes here."])

    extraction = await service.extract_filing_document(filing_version.id)

    assert extraction.extraction_status == EXTRACTION_STATUS_COMPLETED
    assert extraction.page_count == 1

    extraction_repository.create_sections.assert_awaited_once()
    (_, section_rows) = extraction_repository.create_sections.await_args.args
    assert section_rows[0]["heading"] == "ANNUAL REPORT"

    dossier_repository.bulk_create_sources.assert_awaited_once()
    (source_rows,) = dossier_repository.bulk_create_sources.await_args.args
    assert source_rows[0]["source_type"] == "document_extraction"
    assert source_rows[0]["version_id"] == research_version.id
    assert source_rows[0]["reference_id"] == extraction.id

    dossier_repository.create_timeline_event.assert_awaited_once()
    extraction_repository.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_rejects_empty_document():
    filing_version = _filing_version(_filing())
    service, provider, _, extraction_repository, _ = _make_service(filing_version=filing_version)
    provider.extract.return_value = _provider_result([])

    with pytest.raises(InvalidDocumentExtractionError):
        await service.extract_filing_document(filing_version.id)

    extraction_repository.create_extraction.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_does_not_attach_evidence_when_no_research_version_exists_yet():
    filing_version = _filing_version(_filing())
    service, provider, _, extraction_repository, dossier_repository = _make_service(
        filing_version=filing_version, latest_research_version=None
    )
    provider.extract.return_value = _provider_result(["SOME HEADING\nSome body text."])

    await service.extract_filing_document(filing_version.id)

    dossier_repository.get_or_create_dossier.assert_awaited_once()
    dossier_repository.bulk_create_sources.assert_not_awaited()
    dossier_repository.create_timeline_event.assert_not_awaited()
    extraction_repository.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_extraction_raises_not_found_when_missing():
    service, _, _, _, _ = _make_service()

    with pytest.raises(NotFoundError):
        await service.get_extraction(uuid4())


@pytest.mark.asyncio
async def test_get_extraction_returns_stored_extraction():
    stored = DocumentExtraction(
        id=uuid4(),
        filing_version_id=uuid4(),
        company_id=uuid4(),
        extraction_status=EXTRACTION_STATUS_COMPLETED,
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="text",
        page_count=1,
        section_count=1,
    )
    service, _, _, extraction_repository, _ = _make_service()
    extraction_repository.get_by_filing_version.return_value = stored

    result = await service.get_extraction(stored.filing_version_id)
    assert result is stored


@pytest.mark.asyncio
async def test_get_extractions_for_symbol_raises_not_found_for_unknown_company():
    company_repository = AsyncMock()
    company_repository.get_by_symbol.return_value = None
    service = DocumentIntelligenceService(
        provider=AsyncMock(),
        filing_repository=AsyncMock(),
        company_repository=company_repository,
        extraction_repository=AsyncMock(),
        dossier_repository=AsyncMock(),
    )

    with pytest.raises(NotFoundError):
        await service.get_extractions_for_symbol("NOPE")

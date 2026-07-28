"""Document Intelligence Engine service.

Orchestrates provider extraction, normalization, and validation, then
persists the result and links it into the existing Research Dossier as
evidence -- `SOURCE_TYPE_DOCUMENT_EXTRACTION` extends research/models.py's
SourceType catalog for exactly this, the same "extend the catalog, not the
schema" extension point financials/service.py and corporate_filings/service.py
already used. No AI, no LLM calls, no embeddings: every value here is either
copied directly from a mechanically parsed document or computed by plain
counting.

The Corporate Filings module remains the only place filing *discovery*
happens -- this service is handed a `filing_version_id` that already exists
there and never queries a filings provider itself.
"""

import logging
import uuid

from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import FilingVersion
from nivesh.corporate_filings.repository import CorporateFilingRepository
from nivesh.document_intelligence.models import EXTRACTION_STATUS_COMPLETED, DocumentExtraction
from nivesh.document_intelligence.normalization import normalize_extraction
from nivesh.document_intelligence.providers.base import DocumentExtractionProvider
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.document_intelligence.validation import (
    validate_extractable_filing_type,
    validate_no_duplicate_extraction,
    validate_non_empty_document,
    validate_not_corrupted,
    validate_page_consistency,
    validate_section_consistency,
)
from nivesh.research.models import SOURCE_TYPE_DOCUMENT_EXTRACTION
from nivesh.research.repository import ResearchDossierRepository

logger = logging.getLogger(__name__)

PROVIDER_SOURCE_TABLE = "document_extractions"
EVENT_TYPE_DOCUMENT_EXTRACTED = "document_extracted"


class DocumentIntelligenceService:
    def __init__(
        self,
        provider: DocumentExtractionProvider,
        filing_repository: CorporateFilingRepository,
        company_repository: CompanyRepository,
        extraction_repository: DocumentExtractionRepository,
        dossier_repository: ResearchDossierRepository,
    ) -> None:
        self._provider = provider
        self._filings = filing_repository
        self._companies = company_repository
        self._extractions = extraction_repository
        self._dossiers = dossier_repository

    async def extract_filing_document(self, filing_version_id: uuid.UUID) -> DocumentExtraction:
        filing_version = await self._filings.get_version_by_id(filing_version_id)
        if filing_version is None:
            raise NotFoundError(f"No filing version found with id '{filing_version_id}'")

        validate_extractable_filing_type(filing_version.filing.filing_type)

        existing = await self._extractions.get_by_filing_version(filing_version_id)
        validate_no_duplicate_extraction(existing)

        raw = await self._provider.extract(filing_version.source_url)
        validate_page_consistency(raw)

        normalized = normalize_extraction(raw)
        validate_non_empty_document(normalized)
        validate_not_corrupted(normalized)
        validate_section_consistency(normalized.sections)

        extraction = await self._extractions.create_extraction(
            {
                "filing_version_id": filing_version.id,
                "company_id": filing_version.company_id,
                "extraction_status": EXTRACTION_STATUS_COMPLETED,
                "extractor_name": raw.extractor_name,
                "extractor_version": raw.extractor_version,
                "extracted_text": normalized.extracted_text,
                "page_count": normalized.page_count,
                "section_count": normalized.section_count,
            }
        )
        await self._extractions.create_sections(
            extraction.id,
            [
                {
                    "sequence": section.sequence,
                    "heading": section.heading,
                    "level": section.level,
                    "page_number": section.page_number,
                    "content": section.content,
                }
                for section in normalized.sections
            ],
        )
        extraction = await self._extractions.commit_extraction(extraction)

        await self._link_to_research_dossier(filing_version, extraction)

        return extraction

    async def get_extraction(self, filing_version_id: uuid.UUID) -> DocumentExtraction:
        extraction = await self._extractions.get_by_filing_version(filing_version_id)
        if extraction is None:
            raise NotFoundError(
                f"No document extraction exists yet for filing version '{filing_version_id}'"
            )
        return extraction

    async def get_extractions_for_symbol(
        self, symbol: str, limit: int = 50, offset: int = 0
    ) -> list[DocumentExtraction]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._extractions.list_by_company(company.id, limit=limit, offset=offset)

    # -- internals ---------------------------------------------------

    async def _link_to_research_dossier(
        self, filing_version: FilingVersion, extraction: DocumentExtraction
    ) -> None:
        """Records a newly persisted extraction as Research Dossier evidence.

        Sources are attached to the current research version if one already
        exists; version numbering itself stays owned by
        ResearchPipelineService, so this never creates or bumps a research
        version -- only adds evidence to one that already exists.
        """
        company_id = filing_version.company_id
        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "document_extracted_before_research_version",
                extra={"filing_version_id": str(extraction.filing_version_id)},
            )
            return

        await self._dossiers.bulk_create_sources(
            [
                {
                    "dossier_id": dossier.id,
                    "version_id": latest_version.id,
                    "source_type": SOURCE_TYPE_DOCUMENT_EXTRACTION,
                    "reference_table": PROVIDER_SOURCE_TABLE,
                    "reference_id": extraction.id,
                    "range_start": filing_version.filing_date,
                    "range_end": filing_version.filing_date,
                    "record_count": 1,
                }
            ]
        )
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_DOCUMENT_EXTRACTED,
            description=(
                f"Document extracted for filing version '{extraction.filing_version_id}' "
                f"({extraction.page_count} page(s), {extraction.section_count} section(s))."
            ),
            version_id=latest_version.id,
        )
        await self._extractions.commit()

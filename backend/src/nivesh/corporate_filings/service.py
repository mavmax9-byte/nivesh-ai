"""Corporate Filings Metadata Engine service.

Orchestrates provider fetches, validation, normalization, and persistence,
then links the results into the existing Research Dossier as evidence.
`SOURCE_TYPE_CORPORATE_FILING` extends research/models.py's SourceType
catalog for exactly this -- the same "extend the catalog, not the schema"
extension point financials/service.py already used for
SOURCE_TYPE_FINANCIAL_DATA. No AI, no LLM calls, no document parsing:
every value here is either copied directly from a provider-sourced filing
or assigned deterministically (category assignment via a fixed
filing_type -> category lookup table in normalization.py).
"""

import logging
import uuid
from dataclasses import dataclass

from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.corporate_filings.models import (
    ANNUAL_FILING_TYPES,
    QUARTERLY_FILING_TYPES,
    CorporateFiling,
    FilingVersion,
)
from nivesh.corporate_filings.normalization import (
    category_for_filing_type,
    normalize_filing,
    normalize_filing_version,
)
from nivesh.corporate_filings.providers.base import CorporateFilingsProvider, ProviderFiling
from nivesh.corporate_filings.repository import (
    CorporateFilingRepository,
    FilingCategoryRepository,
    FilingSourceRepository,
)
from nivesh.corporate_filings.validation import (
    InvalidFilingDataError,
    is_duplicate_filing,
    validate_checksum_format,
    validate_filing_type,
    validate_reporting_period,
    validate_required_fields,
    validate_source_url,
    validate_version_sequence,
)
from nivesh.research.models import SOURCE_TYPE_CORPORATE_FILING
from nivesh.research.repository import ResearchDossierRepository

logger = logging.getLogger(__name__)

PROVIDER_SOURCE_CODE = "yfinance-dev"
PROVIDER_SOURCE_NAME = "yfinance (development provider)"
PROVIDER_SOURCE_TABLE = "corporate_filings"
EVENT_TYPE_FILINGS_SYNCED = "filings_synced"


@dataclass(frozen=True)
class FilingSyncResult:
    company_id: uuid.UUID
    symbol: str
    filings_synced: int
    filings_unchanged: int


class CorporateFilingsService:
    def __init__(
        self,
        provider: CorporateFilingsProvider,
        company_repository: CompanyRepository,
        category_repository: FilingCategoryRepository,
        source_repository: FilingSourceRepository,
        filing_repository: CorporateFilingRepository,
        dossier_repository: ResearchDossierRepository,
    ) -> None:
        self._provider = provider
        self._companies = company_repository
        self._categories = category_repository
        self._sources = source_repository
        self._filings = filing_repository
        self._dossiers = dossier_repository

    async def sync_company_filings(self, symbol: str) -> FilingSyncResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        provider_filings = await self._provider.get_filings(symbol)
        source = await self._sources.get_or_create_by_code(
            PROVIDER_SOURCE_CODE, PROVIDER_SOURCE_NAME
        )

        synced: list[CorporateFiling] = []
        unchanged = 0

        for provider_filing in provider_filings:
            filing, was_new = await self._persist_filing(company.id, source.id, provider_filing)
            if was_new:
                synced.append(filing)
            else:
                unchanged += 1

        await self._link_to_research_dossier(company.id, company.symbol, synced)

        return FilingSyncResult(
            company_id=company.id,
            symbol=company.symbol,
            filings_synced=len(synced),
            filings_unchanged=unchanged,
        )

    async def get_filings(
        self, symbol: str, limit: int = 50, offset: int = 0
    ) -> list[CorporateFiling]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._filings.list_by_company(company.id, limit=limit, offset=offset)

    async def get_annual_filings(self, symbol: str, limit: int = 50) -> list[CorporateFiling]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._filings.list_by_filing_types(
            company.id, ANNUAL_FILING_TYPES, limit=limit
        )

    async def get_quarterly_filings(self, symbol: str, limit: int = 50) -> list[CorporateFiling]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._filings.list_by_filing_types(
            company.id, QUARTERLY_FILING_TYPES, limit=limit
        )

    async def get_filings_by_category(
        self, symbol: str, category_code: str, limit: int = 50
    ) -> list[CorporateFiling]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._filings.list_by_category_code(company.id, category_code, limit=limit)

    async def get_filing_history(
        self, symbol: str, limit: int = 50, offset: int = 0
    ) -> list[FilingVersion]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._filings.get_version_history_for_company(
            company.id, limit=limit, offset=offset
        )

    # -- internals -----------------------------------------------------

    async def _persist_filing(
        self, company_id: uuid.UUID, source_id: uuid.UUID, provider_filing: ProviderFiling
    ) -> tuple[CorporateFiling, bool]:
        validate_filing_type(provider_filing.filing_type)
        validate_reporting_period(
            filing_type=provider_filing.filing_type,
            reporting_period=provider_filing.reporting_period,
            filing_date=provider_filing.filing_date,
        )
        validate_source_url(provider_filing.source_url)
        validate_checksum_format(provider_filing.checksum)

        category_code, category_name = category_for_filing_type(provider_filing.filing_type)
        category = await self._categories.get_or_create_by_code(category_code, category_name)

        filing_data = normalize_filing(
            company_id=company_id,
            category_id=category.id,
            source_id=source_id,
            filing=provider_filing,
        )
        validate_required_fields(filing_data)

        existing = await self._filings.get_by_identity(
            company_id, provider_filing.filing_type, provider_filing.reporting_period
        )
        if existing is not None and is_duplicate_filing(existing.checksum, filing_data["checksum"]):
            return existing, False

        checksum_owner = await self._filings.get_by_checksum(filing_data["checksum"])
        if checksum_owner is not None and (existing is None or checksum_owner.id != existing.id):
            raise InvalidFilingDataError(
                f"checksum '{filing_data['checksum']}' is already used by a different filing."
            )

        next_version = existing.version_number + 1 if existing is not None else 1
        validate_version_sequence(existing.version_number if existing else None, next_version)

        if existing is None:
            filing = await self._filings.create_filing(
                {**filing_data, "version_number": next_version}
            )
        else:
            filing = await self._filings.update_filing(
                existing, {**filing_data, "version_number": next_version}
            )

        version_data = normalize_filing_version(
            filing_id=filing.id,
            company_id=company_id,
            version_number=next_version,
            filing_data=filing_data,
        )
        await self._filings.create_filing_version(version_data)

        filing = await self._filings.commit_filing(filing)
        return filing, True

    async def _link_to_research_dossier(
        self, company_id: uuid.UUID, symbol: str, synced_filings: list[CorporateFiling]
    ) -> None:
        """Records newly synced filings as Research Dossier evidence.

        Sources are attached to the current research version if one
        already exists; version numbering itself stays owned by
        ResearchPipelineService, so this never creates or bumps a research
        version -- only adds evidence to one that already exists.
        """
        if not synced_filings:
            return

        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "corporate_filings_synced_before_research_version",
                extra={"symbol": symbol, "filing_count": len(synced_filings)},
            )
            return

        source_rows = [
            {
                "dossier_id": dossier.id,
                "version_id": latest_version.id,
                "source_type": SOURCE_TYPE_CORPORATE_FILING,
                "reference_table": PROVIDER_SOURCE_TABLE,
                "reference_id": filing.id,
                "range_start": filing.filing_date,
                "range_end": filing.filing_date,
                "record_count": 1,
            }
            for filing in synced_filings
        ]
        await self._dossiers.bulk_create_sources(source_rows)
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_FILINGS_SYNCED,
            description=f"{len(synced_filings)} corporate filing(s) synced for '{symbol}'.",
            version_id=latest_version.id,
        )
        await self._filings.commit()

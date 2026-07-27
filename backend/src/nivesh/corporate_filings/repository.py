"""Corporate Filings Metadata Engine data-access layer.

`FilingCategoryRepository` and `FilingSourceRepository` follow the exact
`ExchangeRepository` precedent in companies/repository.py:
`get_or_create_by_code` against a handful of reference rows.

`CorporateFilingRepository` treats one filing (its current row plus its
FilingVersion history) as an aggregate root, the same way
FinancialStatementRepository does in financials/repository.py: writes use
`flush()` and only `commit_filing` -- the last step of persisting one
filing -- actually commits, so a filing's row and its new version snapshot
are always written together or not at all.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivesh.corporate_filings.models import (
    CorporateFiling,
    FilingCategory,
    FilingSource,
    FilingVersion,
)

_DETAIL_OPTIONS = (
    selectinload(CorporateFiling.category),
    selectinload(CorporateFiling.source),
)


class FilingCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_code(self, code: str, name: str) -> FilingCategory:
        result = await self._session.execute(
            select(FilingCategory).where(FilingCategory.code == code)
        )
        category = result.scalar_one_or_none()
        if category is not None:
            return category

        category = FilingCategory(code=code, name=name)
        self._session.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category


class FilingSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_code(self, code: str, name: str) -> FilingSource:
        result = await self._session.execute(select(FilingSource).where(FilingSource.code == code))
        source = result.scalar_one_or_none()
        if source is not None:
            return source

        source = FilingSource(code=code, name=name)
        self._session.add(source)
        await self._session.commit()
        await self._session.refresh(source)
        return source


class CorporateFilingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads ---------------------------------------------------------

    async def get_by_identity(
        self, company_id: uuid.UUID, filing_type: str, reporting_period: str
    ) -> CorporateFiling | None:
        result = await self._session.execute(
            select(CorporateFiling)
            .options(*_DETAIL_OPTIONS)
            .where(
                CorporateFiling.company_id == company_id,
                CorporateFiling.filing_type == filing_type,
                CorporateFiling.reporting_period == reporting_period,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_checksum(self, checksum: str) -> CorporateFiling | None:
        result = await self._session.execute(
            select(CorporateFiling).where(CorporateFiling.checksum == checksum)
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[CorporateFiling]:
        result = await self._session.execute(
            select(CorporateFiling)
            .options(*_DETAIL_OPTIONS)
            .where(CorporateFiling.company_id == company_id)
            .order_by(CorporateFiling.filing_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_filing_types(
        self, company_id: uuid.UUID, filing_types: set[str], limit: int = 50
    ) -> list[CorporateFiling]:
        result = await self._session.execute(
            select(CorporateFiling)
            .options(*_DETAIL_OPTIONS)
            .where(
                CorporateFiling.company_id == company_id,
                CorporateFiling.filing_type.in_(filing_types),
            )
            .order_by(CorporateFiling.filing_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_category_code(
        self, company_id: uuid.UUID, category_code: str, limit: int = 50
    ) -> list[CorporateFiling]:
        result = await self._session.execute(
            select(CorporateFiling)
            .options(*_DETAIL_OPTIONS)
            .join(FilingCategory, CorporateFiling.category_id == FilingCategory.id)
            .where(CorporateFiling.company_id == company_id, FilingCategory.code == category_code)
            .order_by(CorporateFiling.filing_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_reporting_period(
        self, company_id: uuid.UUID, reporting_period: str
    ) -> list[CorporateFiling]:
        result = await self._session.execute(
            select(CorporateFiling)
            .options(*_DETAIL_OPTIONS)
            .where(
                CorporateFiling.company_id == company_id,
                CorporateFiling.reporting_period == reporting_period,
            )
            .order_by(CorporateFiling.filing_date.desc())
        )
        return list(result.scalars().all())

    async def list_by_date_range(
        self, company_id: uuid.UUID, start: date, end: date, limit: int = 200
    ) -> list[CorporateFiling]:
        result = await self._session.execute(
            select(CorporateFiling)
            .options(*_DETAIL_OPTIONS)
            .where(
                CorporateFiling.company_id == company_id,
                CorporateFiling.filing_date >= start,
                CorporateFiling.filing_date <= end,
            )
            .order_by(CorporateFiling.filing_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_version_history_for_company(
        self, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[FilingVersion]:
        result = await self._session.execute(
            select(FilingVersion)
            .where(FilingVersion.company_id == company_id)
            .order_by(FilingVersion.recorded_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # -- writes (flush only, except commit_filing) ----------------------

    async def create_filing(self, data: dict) -> CorporateFiling:
        filing = CorporateFiling(**data)
        self._session.add(filing)
        await self._session.flush()
        return filing

    async def update_filing(self, filing: CorporateFiling, data: dict) -> CorporateFiling:
        for field, value in data.items():
            setattr(filing, field, value)
        filing.ingestion_timestamp = datetime.now(UTC)
        await self._session.flush()
        return filing

    async def create_filing_version(self, data: dict) -> FilingVersion:
        version = FilingVersion(**data)
        self._session.add(version)
        await self._session.flush()
        return version

    async def commit_filing(self, filing: CorporateFiling) -> CorporateFiling:
        """Commits the whole write sequence for one filing -- the one
        write in this repository that is not just a flush."""
        await self._session.commit()
        await self._session.refresh(filing, attribute_names=["category", "source", "versions"])
        return filing

    async def commit(self) -> None:
        """Commits whatever is pending on this repository's session.

        Used by CorporateFilingsService to durably persist Research
        Dossier evidence rows written through ResearchDossierRepository's
        flush-only methods on this same shared session -- see
        CorporateFilingsService._link_to_research_dossier.
        """
        await self._session.commit()

"""Research Dossier data-access layer.

`CompanyResearchDossier` is treated as an aggregate root: creating a new
version, its snapshot, its evidence sources, and its timeline entry must
succeed or fail together, so every write method below uses `flush()`
(visible within the transaction, not yet durable) rather than `commit()`.
Only `finalize_version`, the last step of a refresh, commits -- making one
call to `ResearchPipelineService.refresh_dossier` one atomic transaction.
This is a deliberate, narrow exception to the "each repository method
commits its own write" convention used elsewhere (companies, market_data),
justified by the sprint's "never overwrites historical research" /
versioning-integrity requirement: a partially-written version would be
exactly the kind of broken history that requirement rules out.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivesh.research.models import (
    CompanyResearchDossier,
    ResearchSnapshot,
    ResearchSource,
    ResearchTimeline,
    ResearchVersion,
)


class ResearchDossierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -----------------------------------------------------------

    async def get_by_company_id(self, company_id: uuid.UUID) -> CompanyResearchDossier | None:
        result = await self._session.execute(
            select(CompanyResearchDossier).where(CompanyResearchDossier.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_version(self, dossier_id: uuid.UUID) -> ResearchVersion | None:
        result = await self._session.execute(
            select(ResearchVersion)
            .options(selectinload(ResearchVersion.snapshot))
            .where(ResearchVersion.dossier_id == dossier_id)
            .order_by(ResearchVersion.version_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_version_history(
        self, dossier_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[ResearchVersion]:
        result = await self._session.execute(
            select(ResearchVersion)
            .options(selectinload(ResearchVersion.snapshot))
            .where(ResearchVersion.dossier_id == dossier_id)
            .order_by(ResearchVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_recent_timeline(
        self, dossier_id: uuid.UUID, limit: int = 20
    ) -> list[ResearchTimeline]:
        result = await self._session.execute(
            select(ResearchTimeline)
            .where(ResearchTimeline.dossier_id == dossier_id)
            .order_by(ResearchTimeline.event_timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_evidence_counts(self, version_id: uuid.UUID) -> dict[str, int]:
        result = await self._session.execute(
            select(ResearchSource.source_type, func.sum(ResearchSource.record_count))
            .where(ResearchSource.version_id == version_id)
            .group_by(ResearchSource.source_type)
        )
        return {source_type: int(total) for source_type, total in result.all()}

    # -- writes (flush only -- see module docstring) ----------------------

    async def get_or_create_dossier(self, company_id: uuid.UUID) -> CompanyResearchDossier:
        dossier = await self.get_by_company_id(company_id)
        if dossier is not None:
            return dossier

        dossier = CompanyResearchDossier(company_id=company_id)
        self._session.add(dossier)
        await self._session.flush()
        return dossier

    async def create_version(
        self,
        *,
        dossier_id: uuid.UUID,
        version_number: int,
        triggered_by: str,
        change_summary: str,
    ) -> ResearchVersion:
        version = ResearchVersion(
            dossier_id=dossier_id,
            version_number=version_number,
            triggered_by=triggered_by,
            change_summary=change_summary,
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def create_snapshot(
        self,
        *,
        version_id: uuid.UUID,
        company_id: uuid.UUID,
        sector: str | None,
        industry: str | None,
        latest_price: Decimal | None,
        latest_trade_date: date | None,
        price_bar_count: int,
        price_history_start: date | None,
        price_history_end: date | None,
        corporate_action_count: int,
        latest_corporate_action_date: date | None,
    ) -> ResearchSnapshot:
        snapshot = ResearchSnapshot(
            version_id=version_id,
            company_id=company_id,
            sector=sector,
            industry=industry,
            latest_price=latest_price,
            latest_trade_date=latest_trade_date,
            price_bar_count=price_bar_count,
            price_history_start=price_history_start,
            price_history_end=price_history_end,
            corporate_action_count=corporate_action_count,
            latest_corporate_action_date=latest_corporate_action_date,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def bulk_create_sources(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        await self._session.execute(insert(ResearchSource), rows)
        await self._session.flush()
        return len(rows)

    async def create_timeline_event(
        self,
        *,
        dossier_id: uuid.UUID,
        company_id: uuid.UUID,
        event_type: str,
        description: str,
        version_id: uuid.UUID | None = None,
    ) -> ResearchTimeline:
        event = ResearchTimeline(
            dossier_id=dossier_id,
            company_id=company_id,
            event_type=event_type,
            description=description,
            version_id=version_id,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def finalize_version(
        self,
        *,
        dossier: CompanyResearchDossier,
        version_number: int,
        watermark: dict,
    ) -> CompanyResearchDossier:
        """Commits the whole refresh transaction -- the one write in this
        repository that is not just a flush."""
        dossier.current_version_number = version_number
        dossier.last_market_data_watermark = watermark
        await self._session.commit()
        await self._session.refresh(dossier)
        return dossier

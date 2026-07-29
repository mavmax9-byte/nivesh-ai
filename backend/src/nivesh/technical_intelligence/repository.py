"""Technical Intelligence Engine data-access layer.

Bulk upsert is the primary write path, mirroring market_data's own
`bulk_upsert` -- a single generation run writes many indicator rows across
many dates and indicator names, always written (and conflict-resolved) as
a batch. This matches the fact that every value here is a pure
recomputation (re-running generation should never produce a "new version,"
just an updated value for the same identity -- see models.py's module
docstring), so each repository write commits its own batch directly rather
than following the flush-then-final-commit aggregate-root convention used
by modules with parent/child rows that must land together.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.technical_intelligence.models import TechnicalIndicator


class TechnicalIndicatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -----------------------------------------------------------

    async def get_last_indicator_value(
        self, company_id: uuid.UUID, indicator_name: str
    ) -> TechnicalIndicator | None:
        result = await self._session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.company_id == company_id,
                TechnicalIndicator.indicator_name == indicator_name,
            )
            .order_by(TechnicalIndicator.trading_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_snapshot(self, company_id: uuid.UUID) -> list[TechnicalIndicator]:
        """One row per indicator_name -- the most recent trading_date each
        currently has a value for. Uses `DISTINCT ON`, the same
        Postgres-specific "latest row per group" idiom corporate_filings
        and financials use.
        """
        result = await self._session.execute(
            select(TechnicalIndicator)
            .distinct(TechnicalIndicator.indicator_name)
            .where(TechnicalIndicator.company_id == company_id)
            .order_by(TechnicalIndicator.indicator_name, TechnicalIndicator.trading_date.desc())
        )
        return list(result.scalars().all())

    async def get_history(
        self, company_id: uuid.UUID, limit: int = 200, offset: int = 0
    ) -> list[TechnicalIndicator]:
        result = await self._session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.company_id == company_id)
            .order_by(TechnicalIndicator.trading_date.desc(), TechnicalIndicator.indicator_name)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_history_by_indicator(
        self, company_id: uuid.UUID, indicator_name: str, limit: int = 200, offset: int = 0
    ) -> list[TechnicalIndicator]:
        result = await self._session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.company_id == company_id,
                TechnicalIndicator.indicator_name == indicator_name,
            )
            .order_by(TechnicalIndicator.trading_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # -- writes ------------------------------------------------------------

    async def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        statement = pg_insert(TechnicalIndicator).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["company_id", "trading_date", "indicator_name"],
            set_={
                "indicator_parameters": statement.excluded.indicator_parameters,
                "indicator_value": statement.excluded.indicator_value,
                "calculation_timestamp": statement.excluded.calculation_timestamp,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()
        return len(rows)

    async def commit(self) -> None:
        """Commits whatever is pending on this repository's session --
        used by TechnicalIntelligenceService to durably persist Research
        Dossier evidence rows written through ResearchDossierRepository's
        flush-only methods on this same shared session (see
        TechnicalIntelligenceService._link_to_research_dossier).
        """
        await self._session.commit()

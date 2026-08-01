"""Market Universe data-access layer."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.market_universe.models import (
    STATUS_FAILED,
    STATUS_INGESTING,
    STATUS_READY,
    UniverseConstituent,
)


class UniverseConstituentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_symbol(self, index_name: str, symbol: str) -> UniverseConstituent | None:
        result = await self._session.execute(
            select(UniverseConstituent).where(
                UniverseConstituent.index_name == index_name,
                UniverseConstituent.symbol == symbol.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_index(
        self, index_name: str, statuses: set[str] | None = None
    ) -> list[UniverseConstituent]:
        query = select(UniverseConstituent).where(UniverseConstituent.index_name == index_name)
        if statuses:
            query = query.where(UniverseConstituent.ingestion_status.in_(statuses))
        query = query.order_by(UniverseConstituent.symbol)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def seed(self, index_name: str, symbols: tuple[str, ...]) -> int:
        """Creates a constituent row for every symbol not already tracked
        under this index. Idempotent -- existing rows (and their ingestion
        progress) are left untouched, so re-seeding after a partial or
        stale universe never resets work already done."""
        existing = await self.list_by_index(index_name)
        existing_symbols = {c.symbol for c in existing}
        created = 0
        for symbol in symbols:
            if symbol.upper() in existing_symbols:
                continue
            self._session.add(UniverseConstituent(index_name=index_name, symbol=symbol.upper()))
            created += 1
        if created:
            await self._session.commit()
        return created

    async def mark_ingesting(self, constituent: UniverseConstituent) -> None:
        constituent.ingestion_status = STATUS_INGESTING
        constituent.ingestion_error = None
        await self._session.commit()

    async def mark_ready(self, constituent: UniverseConstituent, company_id: uuid.UUID) -> None:
        constituent.ingestion_status = STATUS_READY
        constituent.company_id = company_id
        constituent.ingestion_error = None
        constituent.last_ingested_at = datetime.now(UTC)
        await self._session.commit()

    async def mark_failed(self, constituent: UniverseConstituent, reason: str) -> None:
        constituent.ingestion_status = STATUS_FAILED
        constituent.ingestion_error = reason[:500]
        await self._session.commit()

    async def update_screening(
        self, constituent: UniverseConstituent, score: float, is_screened_in: bool
    ) -> None:
        constituent.screening_score = score
        constituent.is_screened_in = is_screened_in
        constituent.screened_at = datetime.now(UTC)
        await self._session.commit()

    async def get_screening_scores(self, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
        """Used by `portfolio_planner` to prefer screened-in candidates when
        capping its own universe shortlist (PROJECT_CONTEXT.md §13 point
        1f/1g) -- a plain cross-module read via this owning repository,
        never a shared ORM relationship. Companies with no computed score
        (not tracked by any universe, or not yet screened) are simply
        absent from the returned dict; callers must handle that as "no
        preference," not an error."""
        if not company_ids:
            return {}
        result = await self._session.execute(
            select(UniverseConstituent.company_id, UniverseConstituent.screening_score).where(
                UniverseConstituent.company_id.in_(company_ids),
                UniverseConstituent.screening_score.is_not(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

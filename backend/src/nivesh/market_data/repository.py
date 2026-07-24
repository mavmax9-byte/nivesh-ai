"""Market data access layer.

Bulk upsert is the primary write path -- a single sync can involve years of
daily bars, so rows are always written (and conflict-resolved) as a batch,
never one row at a time.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.market_data.models import CorporateAction, HistoricalOHLCV


class HistoricalOHLCVRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        statement = pg_insert(HistoricalOHLCV).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["company_id", "trade_date"],
            set_={
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "volume": statement.excluded.volume,
                "source": statement.excluded.source,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()
        return len(rows)

    async def list_for_company(
        self,
        company_id: uuid.UUID,
        start: date | None = None,
        end: date | None = None,
        limit: int = 1000,
    ) -> list[HistoricalOHLCV]:
        query = select(HistoricalOHLCV).where(HistoricalOHLCV.company_id == company_id)
        if start is not None:
            query = query.where(HistoricalOHLCV.trade_date >= start)
        if end is not None:
            query = query.where(HistoricalOHLCV.trade_date <= end)
        query = query.order_by(HistoricalOHLCV.trade_date.desc()).limit(limit)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_summary_for_company(self, company_id: uuid.UUID) -> dict:
        """Count and date range without loading every row -- used by the
        research pipeline, which only needs aggregate facts, not the bars
        themselves."""
        result = await self._session.execute(
            select(
                func.count(HistoricalOHLCV.id),
                func.min(HistoricalOHLCV.trade_date),
                func.max(HistoricalOHLCV.trade_date),
            ).where(HistoricalOHLCV.company_id == company_id)
        )
        count, start_date, end_date = result.one()
        return {"count": count or 0, "start_date": start_date, "end_date": end_date}


class CorporateActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        statement = pg_insert(CorporateAction).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["company_id", "action_type", "ex_date"],
            set_={
                "ratio_numerator": statement.excluded.ratio_numerator,
                "ratio_denominator": statement.excluded.ratio_denominator,
                "dividend_amount_per_share": statement.excluded.dividend_amount_per_share,
                "source": statement.excluded.source,
            },
        )
        await self._session.execute(statement)
        await self._session.commit()
        return len(rows)

    async def list_for_company(self, company_id: uuid.UUID) -> list[CorporateAction]:
        result = await self._session.execute(
            select(CorporateAction)
            .where(CorporateAction.company_id == company_id)
            .order_by(CorporateAction.ex_date.desc())
        )
        return list(result.scalars().all())

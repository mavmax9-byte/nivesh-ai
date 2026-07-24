"""Portfolio data-access layer."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.portfolios.models import Portfolio
from nivesh.portfolios.schemas import PortfolioCreate


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[Portfolio]:
        result = await self._session.execute(
            select(Portfolio).where(
                Portfolio.tenant_id == tenant_id, Portfolio.user_id == user_id
            )
        )
        return list(result.scalars().all())

    async def create(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, data: PortfolioCreate
    ) -> Portfolio:
        portfolio = Portfolio(tenant_id=tenant_id, user_id=user_id, name=data.name)
        self._session.add(portfolio)
        await self._session.commit()
        await self._session.refresh(portfolio)
        return portfolio

"""Portfolio domain service (placeholder).

Portfolio analytics (allocation, risk metrics, per docs/db 14-Portfolio-Module.md)
are produced by the Portfolio Analysis Agent, not this service -- this layer
only manages the user's declared holdings, never brokerage execution.
"""

import uuid

from nivesh.portfolios.models import Portfolio
from nivesh.portfolios.repository import PortfolioRepository
from nivesh.portfolios.schemas import PortfolioCreate


class PortfolioService:
    def __init__(self, repository: PortfolioRepository) -> None:
        self._repository = repository

    async def list_portfolios(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[Portfolio]:
        return await self._repository.list_for_user(tenant_id, user_id)

    async def create_portfolio(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, data: PortfolioCreate
    ) -> Portfolio:
        return await self._repository.create(tenant_id, user_id, data)

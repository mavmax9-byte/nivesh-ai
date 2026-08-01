"""Portfolio Planner data-access layer.

`PlannedPortfolioRepository` is a genuine aggregate root (a portfolio and
its holdings must land together or not at all), the same shape
`ResearchDossierRepository`/`FinancialStatementRepository` already use --
every write here is `flush()` except the final `commit_portfolio`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivesh.portfolio_planner.models import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_READY,
    PlannedPortfolio,
    PlannedPortfolioHolding,
)


class PlannedPortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, portfolio_id: uuid.UUID) -> PlannedPortfolio | None:
        result = await self._session.execute(
            select(PlannedPortfolio)
            .options(selectinload(PlannedPortfolio.holdings))
            .where(PlannedPortfolio.id == portfolio_id)
        )
        return result.scalar_one_or_none()

    async def create_generating(
        self,
        *,
        capital: float,
        risk_profile: str,
        horizon: str,
        sector_exclusions: list[str],
    ) -> PlannedPortfolio:
        portfolio = PlannedPortfolio(
            capital=capital,
            risk_profile=risk_profile,
            horizon=horizon,
            sector_exclusions=sector_exclusions,
            status=STATUS_GENERATING,
            caveats=[],
        )
        self._session.add(portfolio)
        await self._session.commit()
        await self._session.refresh(portfolio)
        return portfolio

    async def add_holding(self, portfolio_id: uuid.UUID, data: dict) -> PlannedPortfolioHolding:
        holding = PlannedPortfolioHolding(portfolio_id=portfolio_id, **data)
        self._session.add(holding)
        await self._session.flush()
        return holding

    async def mark_ready(
        self,
        portfolio: PlannedPortfolio,
        *,
        summary: str,
        caveats: list[str],
        unallocated_amount: float,
        confidence_score: float,
        evidence_sufficiency: str,
        universe_size: int,
    ) -> PlannedPortfolio:
        portfolio.status = STATUS_READY
        portfolio.summary = summary
        portfolio.caveats = caveats
        portfolio.unallocated_amount = unallocated_amount
        portfolio.confidence_score = confidence_score
        portfolio.evidence_sufficiency = evidence_sufficiency
        portfolio.universe_size = universe_size
        await self._session.commit()
        await self._session.refresh(portfolio)
        return portfolio

    async def mark_failed(self, portfolio: PlannedPortfolio, *, reason: str) -> PlannedPortfolio:
        portfolio.status = STATUS_FAILED
        portfolio.failure_reason = reason
        await self._session.commit()
        await self._session.refresh(portfolio)
        return portfolio

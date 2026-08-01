"""Portfolio Planner routes.

`POST /planner/portfolios` creates the portfolio row immediately
(`status="generating"`) and enqueues the actual work as a Celery task
(`generate_planned_portfolio`, `ingestion/tasks.py`) -- generation can
involve several full Investment Committee runs (5-6 LLM calls each), the
same async-job shape `POST /reports` already uses. `GET
/planner/portfolios/{id}` always returns `200` with a `status` field
(`generating`/`ready`/`failed`) rather than `404`-until-ready: a
multi-minute job with a real, addressable id benefits from a pollable
resource that exists from creation, unlike a specialist/committee
finding (keyed by symbol, not a job id, and legitimately absent until a
report has ever been generated at all). No authentication -- per
INVESTMENT_PLANNER_DESIGN.md §2, this version deliberately asks for
nothing that would need it.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import generate_planned_portfolio
from nivesh.portfolio_planner.repository import PlannedPortfolioRepository
from nivesh.portfolio_planner.schemas import (
    PlannedPortfolioJobStatus,
    PlannedPortfolioRead,
    PlannerRequest,
    RebalanceRead,
)

router = APIRouter(prefix="/planner/portfolios", tags=["portfolio-planner"])


@router.post("", response_model=PlannedPortfolioJobStatus, status_code=202)
async def create_planned_portfolio(
    payload: PlannerRequest,
    db: AsyncSession = Depends(get_db),
) -> PlannedPortfolioJobStatus:
    portfolio = await PlannedPortfolioRepository(db).create_generating(
        capital=payload.capital,
        risk_profile=payload.risk_profile,
        horizon=payload.horizon,
        sector_exclusions=payload.sector_exclusions,
    )
    generate_planned_portfolio.delay(str(portfolio.id))
    return PlannedPortfolioJobStatus(id=portfolio.id, status="generating")


@router.get("/{portfolio_id}", response_model=PlannedPortfolioRead)
async def get_planned_portfolio(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PlannedPortfolioRead:
    portfolio = await PlannedPortfolioRepository(db).get_by_id(portfolio_id)
    if portfolio is None:
        raise NotFoundError(f"No planned portfolio found with id '{portfolio_id}'")
    return PlannedPortfolioRead.model_validate(portfolio)


@router.get("/{portfolio_id}/rebalance", response_model=RebalanceRead)
async def get_rebalance_suggestion(
    portfolio_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RebalanceRead:
    """v1.1 placeholder -- see INVESTMENT_PLANNER_DESIGN.md §10 and
    `schemas.RebalanceRead`'s own docstring. Still validates the
    portfolio id exists, so a bad id surfaces a real 404, not a
    placeholder for a portfolio that was never generated."""
    portfolio = await PlannedPortfolioRepository(db).get_by_id(portfolio_id)
    if portfolio is None:
        raise NotFoundError(f"No planned portfolio found with id '{portfolio_id}'")
    return RebalanceRead()

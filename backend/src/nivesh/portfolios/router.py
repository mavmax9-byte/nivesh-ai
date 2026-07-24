"""Portfolio domain routes.

Every route here requires an authenticated user (placeholder auth, see
core/security.py) since portfolio data is user-scoped, never shared reference
data.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.dependencies import CurrentUser, get_current_user, get_db
from nivesh.portfolios.repository import PortfolioRepository
from nivesh.portfolios.schemas import PortfolioCreate, PortfolioRead
from nivesh.portfolios.service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def get_portfolio_service(db: AsyncSession = Depends(get_db)) -> PortfolioService:
    return PortfolioService(PortfolioRepository(db))


@router.get("", response_model=list[PortfolioRead])
async def list_portfolios(
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[PortfolioRead]:
    portfolios = await service.list_portfolios(
        tenant_id=uuid.UUID(int=0), user_id=uuid.UUID(current_user.id)
    )
    return [PortfolioRead.model_validate(p) for p in portfolios]


@router.post("", response_model=PortfolioRead, status_code=201)
async def create_portfolio(
    payload: PortfolioCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioRead:
    portfolio = await service.create_portfolio(
        tenant_id=uuid.UUID(int=0), user_id=uuid.UUID(current_user.id), data=payload
    )
    return PortfolioRead.model_validate(portfolio)

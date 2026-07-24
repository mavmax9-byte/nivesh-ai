"""Market data domain routes."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import sync_company_market_data
from nivesh.market_data.providers.factory import get_market_data_provider
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.market_data.schemas import HistoricalOHLCVRead, MarketSyncResponse
from nivesh.market_data.service import MarketDataService

router = APIRouter(prefix="/market", tags=["market-data"])


def get_market_data_service(db: AsyncSession = Depends(get_db)) -> MarketDataService:
    return MarketDataService(
        provider=get_market_data_provider(),
        company_repository=CompanyRepository(db),
        exchange_repository=ExchangeRepository(db),
        ohlcv_repository=HistoricalOHLCVRepository(db),
        corporate_action_repository=CorporateActionRepository(db),
    )


@router.post("/sync/{symbol}", response_model=MarketSyncResponse, status_code=202)
async def sync_market_data(symbol: str) -> MarketSyncResponse:
    task = sync_company_market_data.delay(symbol.upper())
    return MarketSyncResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@router.get("/history/{symbol}", response_model=list[HistoricalOHLCVRead])
async def get_market_history(
    symbol: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(default=1000, le=5000),
    service: MarketDataService = Depends(get_market_data_service),
) -> list[HistoricalOHLCVRead]:
    bars = await service.get_history(symbol, start=start, end=end, limit=limit)
    return [HistoricalOHLCVRead.model_validate(b) for b in bars]

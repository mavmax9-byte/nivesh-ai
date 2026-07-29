"""Technical Intelligence Engine routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import generate_technical_indicators
from nivesh.market_data.repository import HistoricalOHLCVRepository
from nivesh.research.repository import ResearchDossierRepository
from nivesh.technical_intelligence.providers.factory import get_technical_data_provider
from nivesh.technical_intelligence.repository import TechnicalIndicatorRepository
from nivesh.technical_intelligence.schemas import (
    TechnicalIndicatorGenerationResponse,
    TechnicalIndicatorRead,
)
from nivesh.technical_intelligence.service import TechnicalIntelligenceService

router = APIRouter(prefix="/technical", tags=["technical-intelligence"])


def get_technical_intelligence_service(
    db: AsyncSession = Depends(get_db),
) -> TechnicalIntelligenceService:
    ohlcv_repository = HistoricalOHLCVRepository(db)
    return TechnicalIntelligenceService(
        provider=get_technical_data_provider(ohlcv_repository),
        company_repository=CompanyRepository(db),
        indicator_repository=TechnicalIndicatorRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@router.post(
    "/generate/{symbol}", response_model=TechnicalIndicatorGenerationResponse, status_code=202
)
async def generate_indicators(symbol: str) -> TechnicalIndicatorGenerationResponse:
    task = generate_technical_indicators.delay(symbol.upper())
    return TechnicalIndicatorGenerationResponse(
        symbol=symbol.upper(), status="queued", task_id=task.id
    )


@router.get("/{symbol}/latest", response_model=list[TechnicalIndicatorRead])
async def get_latest_indicators(
    symbol: str,
    service: TechnicalIntelligenceService = Depends(get_technical_intelligence_service),
) -> list[TechnicalIndicatorRead]:
    indicators = await service.get_latest_indicators(symbol)
    return [TechnicalIndicatorRead.model_validate(i) for i in indicators]


@router.get("/{symbol}/history", response_model=list[TechnicalIndicatorRead])
async def get_indicator_history(
    symbol: str,
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TechnicalIntelligenceService = Depends(get_technical_intelligence_service),
) -> list[TechnicalIndicatorRead]:
    indicators = await service.get_indicator_history(symbol, limit=limit, offset=offset)
    return [TechnicalIndicatorRead.model_validate(i) for i in indicators]


@router.get("/{symbol}/indicator/{indicator_name}", response_model=list[TechnicalIndicatorRead])
async def get_indicators_by_name(
    symbol: str,
    indicator_name: str,
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TechnicalIntelligenceService = Depends(get_technical_intelligence_service),
) -> list[TechnicalIndicatorRead]:
    indicators = await service.get_indicators_by_name(
        symbol, indicator_name, limit=limit, offset=offset
    )
    return [TechnicalIndicatorRead.model_validate(i) for i in indicators]

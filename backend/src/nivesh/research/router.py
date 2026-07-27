"""Research Dossier routes."""

from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.dependencies import get_db
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.research.repository import ResearchDossierRepository
from nivesh.research.schemas import (
    ResearchDossierRead,
    ResearchEvidenceSummary,
    ResearchTimelineEventRead,
    ResearchVersionRead,
    SourceType,
)
from nivesh.research.service import ResearchPipelineService

router = APIRouter(prefix="/research", tags=["research"])


def get_research_service(db: AsyncSession = Depends(get_db)) -> ResearchPipelineService:
    return ResearchPipelineService(
        company_repository=CompanyRepository(db),
        dossier_repository=ResearchDossierRepository(db),
        ohlcv_repository=HistoricalOHLCVRepository(db),
        corporate_action_repository=CorporateActionRepository(db),
    )


@router.get("/{symbol}", response_model=ResearchDossierRead)
async def get_research_dossier(
    symbol: str, service: ResearchPipelineService = Depends(get_research_service)
) -> ResearchDossierRead:
    overview = await service.get_dossier_overview(symbol)
    return ResearchDossierRead(
        symbol=overview.symbol,
        current_version_number=overview.current_version_number,
        last_refreshed_at=overview.last_refreshed_at,
        latest_version=ResearchVersionRead.model_validate(overview.latest_version)
        if overview.latest_version
        else None,
        recent_timeline=[
            ResearchTimelineEventRead.model_validate(event) for event in overview.recent_timeline
        ],
        evidence_summary=[
            # evidence_counts keys are always one of the SOURCE_TYPE_* constants
            # (research/models.py) -- get_evidence_counts just can't say so at the
            # type level since it groups by a plain string column.
            ResearchEvidenceSummary(source_type=cast(SourceType, source_type), record_count=count)
            for source_type, count in overview.evidence_counts.items()
        ],
    )


@router.get("/{symbol}/history", response_model=list[ResearchVersionRead])
async def get_research_history(
    symbol: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: ResearchPipelineService = Depends(get_research_service),
) -> list[ResearchVersionRead]:
    versions = await service.get_version_history(symbol, limit=limit, offset=offset)
    return [ResearchVersionRead.model_validate(v) for v in versions]


@router.get("/{symbol}/latest", response_model=ResearchVersionRead)
async def get_research_latest(
    symbol: str, service: ResearchPipelineService = Depends(get_research_service)
) -> ResearchVersionRead:
    version = await service.get_latest_version(symbol)
    return ResearchVersionRead.model_validate(version)

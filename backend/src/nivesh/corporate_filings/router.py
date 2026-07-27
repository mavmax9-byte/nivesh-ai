"""Corporate Filings Metadata Engine routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.corporate_filings.providers.factory import get_corporate_filings_provider
from nivesh.corporate_filings.repository import (
    CorporateFilingRepository,
    FilingCategoryRepository,
    FilingSourceRepository,
)
from nivesh.corporate_filings.schemas import (
    CorporateFilingRead,
    FilingSyncResponse,
    FilingVersionRead,
)
from nivesh.corporate_filings.service import CorporateFilingsService
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import sync_company_filings
from nivesh.research.repository import ResearchDossierRepository

router = APIRouter(prefix="/filings", tags=["corporate-filings"])


def get_corporate_filings_service(db: AsyncSession = Depends(get_db)) -> CorporateFilingsService:
    return CorporateFilingsService(
        provider=get_corporate_filings_provider(),
        company_repository=CompanyRepository(db),
        category_repository=FilingCategoryRepository(db),
        source_repository=FilingSourceRepository(db),
        filing_repository=CorporateFilingRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@router.post("/sync/{symbol}", response_model=FilingSyncResponse, status_code=202)
async def sync_filings(symbol: str) -> FilingSyncResponse:
    task = sync_company_filings.delay(symbol.upper())
    return FilingSyncResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@router.get("/{symbol}", response_model=list[CorporateFilingRead])
async def get_filings(
    symbol: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: CorporateFilingsService = Depends(get_corporate_filings_service),
) -> list[CorporateFilingRead]:
    filings = await service.get_filings(symbol, limit=limit, offset=offset)
    return [CorporateFilingRead.model_validate(f) for f in filings]


@router.get("/{symbol}/annual", response_model=list[CorporateFilingRead])
async def get_annual_filings(
    symbol: str,
    limit: int = Query(default=50, le=200),
    service: CorporateFilingsService = Depends(get_corporate_filings_service),
) -> list[CorporateFilingRead]:
    filings = await service.get_annual_filings(symbol, limit=limit)
    return [CorporateFilingRead.model_validate(f) for f in filings]


@router.get("/{symbol}/quarterly", response_model=list[CorporateFilingRead])
async def get_quarterly_filings(
    symbol: str,
    limit: int = Query(default=50, le=200),
    service: CorporateFilingsService = Depends(get_corporate_filings_service),
) -> list[CorporateFilingRead]:
    filings = await service.get_quarterly_filings(symbol, limit=limit)
    return [CorporateFilingRead.model_validate(f) for f in filings]


@router.get("/{symbol}/category/{category}", response_model=list[CorporateFilingRead])
async def get_filings_by_category(
    symbol: str,
    category: str,
    limit: int = Query(default=50, le=200),
    service: CorporateFilingsService = Depends(get_corporate_filings_service),
) -> list[CorporateFilingRead]:
    filings = await service.get_filings_by_category(symbol, category, limit=limit)
    return [CorporateFilingRead.model_validate(f) for f in filings]


@router.get("/{symbol}/history", response_model=list[FilingVersionRead])
async def get_filing_history(
    symbol: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: CorporateFilingsService = Depends(get_corporate_filings_service),
) -> list[FilingVersionRead]:
    versions = await service.get_filing_history(symbol, limit=limit, offset=offset)
    return [FilingVersionRead.model_validate(v) for v in versions]

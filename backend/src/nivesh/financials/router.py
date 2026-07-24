"""Financial Statements Engine routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.dependencies import get_db
from nivesh.financials.providers.factory import get_financial_data_provider
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.financials.schemas import (
    FinancialsOverviewRead,
    FinancialStatementRead,
    FinancialSyncResponse,
)
from nivesh.financials.service import FinancialStatementService
from nivesh.ingestion.tasks import sync_company_financials
from nivesh.research.repository import ResearchDossierRepository

router = APIRouter(prefix="/financials", tags=["financials"])


def get_financial_statement_service(
    db: AsyncSession = Depends(get_db),
) -> FinancialStatementService:
    return FinancialStatementService(
        provider=get_financial_data_provider(),
        company_repository=CompanyRepository(db),
        statement_repository=FinancialStatementRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@router.post("/sync/{symbol}", response_model=FinancialSyncResponse, status_code=202)
async def sync_financials(symbol: str) -> FinancialSyncResponse:
    task = sync_company_financials.delay(symbol.upper())
    return FinancialSyncResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@router.get("/{symbol}", response_model=FinancialsOverviewRead)
async def get_financials_overview(
    symbol: str, service: FinancialStatementService = Depends(get_financial_statement_service)
) -> FinancialsOverviewRead:
    overview = await service.get_overview(symbol)
    return FinancialsOverviewRead(
        symbol=overview.symbol,
        latest_annual=FinancialStatementRead.model_validate(overview.latest_annual)
        if overview.latest_annual
        else None,
        latest_quarterly=FinancialStatementRead.model_validate(overview.latest_quarterly)
        if overview.latest_quarterly
        else None,
    )


@router.get("/{symbol}/annual", response_model=list[FinancialStatementRead])
async def get_annual_financials(
    symbol: str,
    limit: int = Query(default=8, le=50),
    service: FinancialStatementService = Depends(get_financial_statement_service),
) -> list[FinancialStatementRead]:
    statements = await service.get_annual_statements(symbol, limit=limit)
    return [FinancialStatementRead.model_validate(s) for s in statements]


@router.get("/{symbol}/quarterly", response_model=list[FinancialStatementRead])
async def get_quarterly_financials(
    symbol: str,
    limit: int = Query(default=8, le=50),
    service: FinancialStatementService = Depends(get_financial_statement_service),
) -> list[FinancialStatementRead]:
    statements = await service.get_quarterly_statements(symbol, limit=limit)
    return [FinancialStatementRead.model_validate(s) for s in statements]

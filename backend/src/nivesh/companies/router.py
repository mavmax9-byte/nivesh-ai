"""Company domain routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.companies.schemas import CompanyRead
from nivesh.companies.service import CompanyService
from nivesh.dependencies import get_db

router = APIRouter(prefix="/companies", tags=["companies"])


def get_company_service(db: AsyncSession = Depends(get_db)) -> CompanyService:
    return CompanyService(CompanyRepository(db))


@router.get("", response_model=list[CompanyRead])
async def list_companies(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: CompanyService = Depends(get_company_service),
) -> list[CompanyRead]:
    companies = await service.list_companies(limit=limit, offset=offset)
    return [CompanyRead.model_validate(c) for c in companies]


@router.get("/{symbol}", response_model=CompanyRead)
async def get_company(
    symbol: str, service: CompanyService = Depends(get_company_service)
) -> CompanyRead:
    company = await service.get_by_symbol(symbol)
    return CompanyRead.model_validate(company)

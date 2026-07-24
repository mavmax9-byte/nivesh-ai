"""Company domain service.

Companies are created/updated exclusively through the Market Data sync flow
(MarketDataService) -- there is no direct company-creation entry point here,
since a company record without provider-sourced metadata behind it would be
exactly the kind of fabricated data this platform's explainability
requirements rule out.
"""

from nivesh.companies.models import Company
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError


class CompanyService:
    def __init__(self, repository: CompanyRepository) -> None:
        self._repository = repository

    async def get_by_symbol(self, symbol: str) -> Company:
        company = await self._repository.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return company

    async def list_companies(self, limit: int = 50, offset: int = 0) -> list[Company]:
        return await self._repository.list(limit=limit, offset=offset)

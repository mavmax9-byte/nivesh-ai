"""Company and Exchange data-access layer.

Thin wrapper over SQLAlchemy -- no business rules live here, only query
construction and persistence.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivesh.companies.models import Company, Exchange

_EXCHANGE_NAMES = {
    "NSE": "National Stock Exchange of India",
    "BSE": "BSE Limited",
}


class ExchangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_code(self, code: str) -> Exchange:
        result = await self._session.execute(select(Exchange).where(Exchange.code == code.upper()))
        exchange = result.scalar_one_or_none()
        if exchange is not None:
            return exchange

        exchange = Exchange(code=code.upper(), name=_EXCHANGE_NAMES.get(code.upper(), code.upper()))
        self._session.add(exchange)
        await self._session.commit()
        await self._session.refresh(exchange)
        return exchange


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_symbol(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company)
            .options(selectinload(Company.exchange))
            .where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 50, offset: int = 0) -> list[Company]:
        result = await self._session.execute(
            select(Company)
            .options(selectinload(Company.exchange))
            .where(Company.is_active.is_(True))
            .order_by(Company.symbol)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        symbol: str,
        name: str,
        exchange_id: uuid.UUID,
        sector: str | None,
        industry: str | None,
    ) -> Company:
        """Create or update a company by symbol.

        Accepts plain fields rather than a provider DTO so this repository
        has no dependency on where the data came from -- a provider sync
        today, potentially a manual admin correction later.
        """
        company = await self.get_by_symbol(symbol)
        if company is None:
            company = Company(
                symbol=symbol.upper(),
                exchange_id=exchange_id,
                name=name,
                sector=sector,
                industry=industry,
            )
            self._session.add(company)
        else:
            company.name = name
            company.sector = sector
            company.industry = industry
            company.exchange_id = exchange_id

        await self._session.commit()
        await self._session.refresh(company, attribute_names=["exchange"])
        return company

"""Company domain response schemas."""

import uuid

from pydantic import BaseModel, ConfigDict


class ExchangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    name: str
    exchange: ExchangeRead
    sector: str | None
    industry: str | None
    is_active: bool

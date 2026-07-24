"""Portfolio domain request/response schemas."""

import uuid

from pydantic import BaseModel, ConfigDict


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class PortfolioCreate(BaseModel):
    name: str

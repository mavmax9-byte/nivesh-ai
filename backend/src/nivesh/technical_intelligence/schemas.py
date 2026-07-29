"""Technical Intelligence Engine response schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TechnicalIndicatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    trading_date: date
    indicator_name: str
    indicator_parameters: dict
    indicator_value: Decimal
    calculation_timestamp: datetime
    created_at: datetime
    updated_at: datetime


class TechnicalIndicatorGenerationResponse(BaseModel):
    symbol: str
    status: str
    task_id: str

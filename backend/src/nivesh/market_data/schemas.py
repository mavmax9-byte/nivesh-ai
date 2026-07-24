"""Market data domain request/response schemas."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class HistoricalOHLCVRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class MarketSyncResponse(BaseModel):
    symbol: str
    status: str
    task_id: str

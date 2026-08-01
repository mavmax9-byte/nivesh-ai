"""Market Universe Pydantic response models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConstituentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    index_name: str
    symbol: str
    company_id: uuid.UUID | None
    ingestion_status: str
    ingestion_error: str | None
    last_ingested_at: datetime | None
    screening_score: float | None
    is_screened_in: bool
    screened_at: datetime | None


class SeedResponse(BaseModel):
    index_name: str
    seeded: int
    total_tracked: int


class SyncRequest(BaseModel):
    symbols: list[str] | None = None


class SyncResponse(BaseModel):
    index_name: str
    queued: list[str]


class ScreenRequest(BaseModel):
    top_n: int | None = None


class ScreenResponse(BaseModel):
    """Screening (and any resulting Investment Committee runs) happens
    asynchronously in a Celery task -- this response only confirms the
    request was queued, not its outcome. Poll `GET /universe` afterward
    to see `is_screened_in`/`screening_score` once the task completes."""

    index_name: str
    top_n: int
    status: str = "queued"

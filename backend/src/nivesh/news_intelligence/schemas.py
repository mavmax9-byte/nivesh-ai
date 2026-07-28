"""News Intelligence Engine response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NewsArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    source: str
    author: str | None
    published_at: datetime
    url: str
    summary: str
    full_content: str | None
    language: str
    category: str
    provider: str
    ingestion_timestamp: datetime
    created_at: datetime
    updated_at: datetime


class NewsSyncResponse(BaseModel):
    symbol: str
    status: str
    task_id: str

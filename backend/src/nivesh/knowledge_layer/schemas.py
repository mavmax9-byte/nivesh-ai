"""Knowledge Layer response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeEmbeddingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str | None
    content_text: str
    embedding_model: str
    embedding_dimensions: int
    created_at: datetime
    updated_at: datetime


class KnowledgeGenerationResponse(BaseModel):
    symbol: str
    status: str
    task_id: str


class KnowledgeSearchResultRead(BaseModel):
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str | None
    content_text: str
    similarity: float


class KnowledgeSearchResponse(BaseModel):
    symbol: str
    query: str
    results: list[KnowledgeSearchResultRead]

"""Retrieval Engine response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EvidenceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str
    snippet: str
    evidence_date: date | None
    relevance_score: float
    retrieved_via: tuple[str, ...]


class RetrievalResponse(BaseModel):
    symbol: str
    query: str
    evidence: list[EvidenceItemRead]


class ContextPackageRead(BaseModel):
    symbol: str
    query: str
    generated_at: datetime
    evidence: list[EvidenceItemRead]
    context_text: str


class RetrievalDiagnosticsRead(BaseModel):
    symbol: str
    query: str
    fetched_counts: dict[str, int]
    total_fetched: int
    total_after_dedup: int
    total_returned: int
    evidence: list[EvidenceItemRead]

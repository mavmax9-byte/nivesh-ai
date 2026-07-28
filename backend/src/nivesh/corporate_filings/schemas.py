"""Corporate Filings Metadata Engine response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class FilingCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class FilingSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class CorporateFilingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exchange: str
    filing_type: str
    category: FilingCategoryRead
    source: FilingSourceRead
    title: str
    reporting_period: str
    filing_date: date
    source_url: str
    checksum: str
    language: str
    document_size: int | None
    version_number: int
    ingestion_timestamp: datetime
    created_at: datetime
    updated_at: datetime


class FilingVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    title: str
    filing_date: date
    source_url: str
    checksum: str
    document_size: int | None
    recorded_at: datetime


class FilingSyncResponse(BaseModel):
    symbol: str
    status: str
    task_id: str

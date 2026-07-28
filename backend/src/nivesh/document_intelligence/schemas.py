"""Document Intelligence Engine response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    heading: str
    level: int
    page_number: int
    content: str


class DocumentExtractionRead(BaseModel):
    """Light-weight extraction summary -- omits `extracted_text` and
    `sections` so listing a company's extraction history stays cheap."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filing_version_id: uuid.UUID
    company_id: uuid.UUID
    extraction_status: str
    extractor_name: str
    extractor_version: str
    page_count: int
    section_count: int
    created_at: datetime
    updated_at: datetime


class DocumentExtractionDetailRead(DocumentExtractionRead):
    """Full extraction, including canonical text and section breakdown --
    returned for a single filing version, never in a list."""

    extracted_text: str
    sections: list[DocumentSectionRead]


class DocumentExtractionSyncResponse(BaseModel):
    filing_version_id: uuid.UUID
    status: str
    task_id: str

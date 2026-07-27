"""Research Dossier response schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal[
    "market_data",
    "financial_data",
    "corporate_action",
    "corporate_filing",
    "news",
    "technical_indicator",
]


class ResearchSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sector: str | None
    industry: str | None
    latest_price: Decimal | None
    latest_trade_date: date | None
    price_bar_count: int
    price_history_start: date | None
    price_history_end: date | None
    corporate_action_count: int
    latest_corporate_action_date: date | None


class ResearchVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_number: int
    triggered_by: str
    change_summary: str
    created_at: datetime
    snapshot: ResearchSnapshotRead | None


class ResearchTimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    description: str
    event_timestamp: datetime


class ResearchEvidenceSummary(BaseModel):
    source_type: SourceType
    record_count: int


class ResearchDossierRead(BaseModel):
    symbol: str
    current_version_number: int
    last_refreshed_at: datetime | None
    latest_version: ResearchVersionRead | None
    recent_timeline: list[ResearchTimelineEventRead]
    evidence_summary: list[ResearchEvidenceSummary]

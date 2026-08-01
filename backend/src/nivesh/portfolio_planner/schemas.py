"""Portfolio Planner request/response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RiskProfile = Literal["conservative", "balanced", "growth"]
Horizon = Literal["short", "medium", "long"]
PortfolioStatus = Literal["generating", "ready", "failed"]
EvidenceSufficiency = Literal["sufficient", "partial", "insufficient"]


class PlannerRequest(BaseModel):
    capital: float = Field(gt=0, description="Investable amount in INR")
    risk_profile: RiskProfile
    horizon: Horizon
    sector_exclusions: list[str] = Field(default_factory=list)


class PlannedPortfolioJobStatus(BaseModel):
    id: uuid.UUID
    status: PortfolioStatus


class HoldingRead(BaseModel):
    company_id: uuid.UUID
    symbol: str
    company_name: str
    sector: str | None
    allocated_amount: float
    allocated_weight: float
    rank_score: float
    confidence_score: float
    evidence_sufficiency: EvidenceSufficiency
    thesis: str
    weight_rationale: str
    top_citation_title: str | None
    top_citation_source_type: str | None

    model_config = {"from_attributes": True}


class PlannedPortfolioRead(BaseModel):
    id: uuid.UUID
    capital: float
    risk_profile: RiskProfile
    horizon: Horizon
    sector_exclusions: list[str]
    status: PortfolioStatus
    summary: str | None
    caveats: list[str]
    unallocated_amount: float | None
    confidence_score: float | None
    evidence_sufficiency: EvidenceSufficiency | None
    universe_size: int | None
    failure_reason: str | None
    holdings: list[HoldingRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RebalanceRead(BaseModel):
    """v1.1 scope: a deliberate placeholder, not a stub bug -- see
    INVESTMENT_PLANNER_DESIGN.md §10. Real drift/time/evidence-change
    triggers need live portfolios accumulating history this version does
    not yet have."""

    available: bool = False
    message: str = (
        "Rebalancing suggestions are not yet available. This capability is "
        "planned for a future version, once portfolios can accumulate real "
        "drift and evidence-change history to trigger against."
    )

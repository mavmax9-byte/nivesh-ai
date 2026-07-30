"""Technical Analyst structured output schemas.

Follows the v1.0 shared two-layer shape (INVESTMENT_COMMITTEE_DESIGN.md
§4): `LLMTechnicalOutput` is exactly what the LLM is asked to produce;
`TechnicalAnalysisResult` is the full persisted/returned shape. Uses the
shared `SpecialistAssessment` (`stance` field) rather than Fundamental's
own `strengths`/`concerns` two-list shape -- "this signals a buy" is
exactly the kind of implied recommendation this agent must never produce,
so `stance` here classifies the *technical reading* (e.g. "momentum is
positive") not a trading signal.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nivesh.ai_agents.guardrails import CitationRef, SpecialistAssessment

EvidenceSufficiency = Literal["sufficient", "partial", "insufficient"]


class LLMTechnicalOutput(BaseModel):
    """The exact shape requested from the LLM via structured output."""

    summary: str
    findings: list[SpecialistAssessment]
    technical_read: str
    evidence_sufficiency: EvidenceSufficiency
    llm_confidence: float = Field(ge=0.0, le=1.0)


class TechnicalAnalysisResult(BaseModel):
    company_symbol: str
    summary: str
    findings: list[SpecialistAssessment]
    technical_read: str
    evidence_sufficiency: EvidenceSufficiency
    confidence_score: float
    citations: list[CitationRef]
    caveats: list[str]
    prompt_version: str
    model_used: str
    generated_at: datetime

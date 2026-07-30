"""Valuation Analyst structured output schemas. Same v1.0 shared two-layer
shape as Technical Analyst (see technical/schemas.py) -- only the
domain-specific field (`valuation_assessment` instead of `technical_read`)
differs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nivesh.ai_agents.guardrails import CitationRef, SpecialistAssessment

EvidenceSufficiency = Literal["sufficient", "partial", "insufficient"]


class LLMValuationOutput(BaseModel):
    """The exact shape requested from the LLM via structured output."""

    summary: str
    findings: list[SpecialistAssessment]
    valuation_assessment: str
    evidence_sufficiency: EvidenceSufficiency
    llm_confidence: float = Field(ge=0.0, le=1.0)


class ValuationAnalysisResult(BaseModel):
    company_symbol: str
    summary: str
    findings: list[SpecialistAssessment]
    valuation_assessment: str
    evidence_sufficiency: EvidenceSufficiency
    confidence_score: float
    citations: list[CitationRef]
    caveats: list[str]
    prompt_version: str
    model_used: str
    generated_at: datetime

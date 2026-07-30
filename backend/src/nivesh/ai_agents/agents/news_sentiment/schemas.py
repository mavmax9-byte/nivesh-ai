"""News & Sentiment Analyst structured output schemas. Same v1.0 shared
two-layer shape as Technical Analyst -- `sentiment_assessment` is the
domain-specific field."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nivesh.ai_agents.guardrails import CitationRef, SpecialistAssessment

EvidenceSufficiency = Literal["sufficient", "partial", "insufficient"]


class LLMNewsSentimentOutput(BaseModel):
    """The exact shape requested from the LLM via structured output."""

    summary: str
    findings: list[SpecialistAssessment]
    sentiment_assessment: str
    evidence_sufficiency: EvidenceSufficiency
    llm_confidence: float = Field(ge=0.0, le=1.0)


class NewsSentimentAnalysisResult(BaseModel):
    company_symbol: str
    summary: str
    findings: list[SpecialistAssessment]
    sentiment_assessment: str
    evidence_sufficiency: EvidenceSufficiency
    confidence_score: float
    citations: list[CitationRef]
    caveats: list[str]
    prompt_version: str
    model_used: str
    generated_at: datetime

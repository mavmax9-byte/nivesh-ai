"""Fundamental Analyst structured output schemas.

Two layers, deliberately not one (see FUNDAMENTAL_ANALYST_DESIGN.md
§6/§8): `LLMFundamentalOutput` is exactly what the LLM itself is asked to
produce (requested via `LLMProvider.complete`'s `json_schema` argument).
`FundamentalAnalysisResult` is the full persisted/returned shape --
`confidence_score` (a deterministic blend, not the model's raw
self-report), `citations` (resolved against the evidence actually shown
to the model), `prompt_version`, `model_used`, and `generated_at` are all
computed in Python after the call, in `agent.py`, never asked of the
model.

`citation_refs` is a plain `list[int]`, not constrained to a minimum
length at the schema level -- an assessment with zero *valid* citations
is dropped by `guardrails.drop_unsupported_assessments` (one claim
removed, not the whole response rejected), which needs to see the
raw list including any empty/invalid ones to do that.

`CitationRef` moved to `ai_agents/guardrails.py` in v1.0 (it was never
Fundamental-specific -- every specialist resolves citations to the same
shape) and is re-imported here so existing callers of this module are
unaffected.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nivesh.ai_agents.guardrails import CitationRef

__all__ = [
    "CitationRef",
    "EvidenceSufficiency",
    "FundamentalMetricAssessment",
    "LLMFundamentalOutput",
    "FundamentalAnalysisResult",
]

EvidenceSufficiency = Literal["sufficient", "partial", "insufficient"]


class FundamentalMetricAssessment(BaseModel):
    metric: str
    observation: str
    citation_refs: list[int]


class LLMFundamentalOutput(BaseModel):
    """The exact shape requested from the LLM via structured output."""

    summary: str
    strengths: list[FundamentalMetricAssessment]
    concerns: list[FundamentalMetricAssessment]
    financial_health_assessment: str
    evidence_sufficiency: EvidenceSufficiency
    llm_confidence: float = Field(ge=0.0, le=1.0)


class FundamentalAnalysisResult(BaseModel):
    company_symbol: str
    summary: str
    strengths: list[FundamentalMetricAssessment]
    concerns: list[FundamentalMetricAssessment]
    financial_health_assessment: str
    evidence_sufficiency: EvidenceSufficiency
    confidence_score: float
    citations: list[CitationRef]
    caveats: list[str]
    prompt_version: str
    model_used: str
    generated_at: datetime

"""Risk-Analyst-specific evidence-confidence weighting.

Coverage-weighted like Fundamental and Valuation's, scoped to this agent's
own three relevant evidence types (queries.py). `document_section` is
weighted highest here (unlike Fundamental's weighting) since explicit
"Risk Factors" filing sections are the single most direct risk-relevant
evidence type available in this codebase today.
"""

from collections.abc import Sequence

from nivesh.ai_agents.guardrails import EVIDENCE_CONFIDENCE_FLOOR
from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_DOCUMENT_SECTION,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
)
from nivesh.retrieval_engine.normalization import EvidenceItem

_SOURCE_TYPE_WEIGHTS: dict[str, float] = {
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT: 0.4,
    EVIDENCE_SOURCE_DOCUMENT_SECTION: 0.4,
    EVIDENCE_SOURCE_CORPORATE_FILING: 0.2,
}


def compute_evidence_confidence(evidence: Sequence[EvidenceItem]) -> float:
    present_types = {item.source_type for item in evidence}
    if not present_types & set(_SOURCE_TYPE_WEIGHTS):
        return EVIDENCE_CONFIDENCE_FLOOR

    coverage = sum(
        weight
        for source_type, weight in _SOURCE_TYPE_WEIGHTS.items()
        if source_type in present_types
    )
    return max(0.0, min(1.0, coverage))

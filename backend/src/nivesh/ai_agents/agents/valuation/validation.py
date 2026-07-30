"""Valuation-Analyst-specific evidence-confidence weighting.

Same coverage-weighted shape as Fundamental Analyst's
(`fundamental/validation.py`), scoped to this agent's own two relevant
evidence types (queries.py) rather than Fundamental's five. Deliberately
does not factor in whether a computed P/E ratio was available (`ratios.py`)
-- that is reflected as a caveat on the finding, not as a confidence
penalty, consistent with how a missing evidence *type* (not a missing
computed convenience value) is what this signal exists to measure.
"""

from collections.abc import Sequence

from nivesh.ai_agents.guardrails import EVIDENCE_CONFIDENCE_FLOOR
from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
)
from nivesh.retrieval_engine.normalization import EvidenceItem

_SOURCE_TYPE_WEIGHTS: dict[str, float] = {
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT: 0.7,
    EVIDENCE_SOURCE_CORPORATE_FILING: 0.3,
}


def compute_evidence_confidence(evidence: Sequence[EvidenceItem]) -> float:
    present_types = {item.source_type for item in evidence}
    if EVIDENCE_SOURCE_FINANCIAL_STATEMENT not in present_types:
        return EVIDENCE_CONFIDENCE_FLOOR

    coverage = sum(
        weight
        for source_type, weight in _SOURCE_TYPE_WEIGHTS.items()
        if source_type in present_types
    )
    return max(0.0, min(1.0, coverage))

"""Fundamental-Analyst-specific evidence-confidence weighting.

The citation-range validation, unsupported-claim dropping, and investment-
advice-language filter that used to live in this module were promoted to
`ai_agents/guardrails.py` during the v1.0 Investment Committee build
(INVESTMENT_COMMITTEE_DESIGN.md §4) -- they were never Fundamental-specific.
`compute_evidence_confidence` and its `_SOURCE_TYPE_WEIGHTS` stay here: which
evidence types matter and how much is a genuinely domain-specific judgment
call (a Technical Analyst would weight `technical_indicator` presence, not
`financial_statement`), so each specialist defines its own version rather
than sharing one.
"""

from collections.abc import Sequence

from nivesh.ai_agents.guardrails import EVIDENCE_CONFIDENCE_FLOOR
from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_DOCUMENT_SECTION,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
    EVIDENCE_SOURCE_RESEARCH_SUMMARY,
)
from nivesh.retrieval_engine.normalization import EvidenceItem

__all__ = ["EVIDENCE_CONFIDENCE_FLOOR", "compute_evidence_confidence"]

_SOURCE_TYPE_WEIGHTS: dict[str, float] = {
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT: 0.6,
    EVIDENCE_SOURCE_CORPORATE_FILING: 0.2,
    EVIDENCE_SOURCE_DOCUMENT_SECTION: 0.1,
    EVIDENCE_SOURCE_RESEARCH_SUMMARY: 0.1,
}


def compute_evidence_confidence(evidence: Sequence[EvidenceItem]) -> float:
    """Deterministic, pre-LLM confidence signal computed purely from what
    retrieval_engine returned, before the LLM is ever called. The model's
    own self-reported confidence (see guardrails.compute_confidence_score)
    can only lower this, never raise it -- see FUNDAMENTAL_ANALYST_DESIGN.md
    §8. A finding with zero financial_statement evidence cannot meaningfully
    assess "financial fundamentals" no matter what the model claims -- this
    floor forces evidence_confidence low regardless of other evidence
    present, and agent.py short-circuits the LLM call entirely at this
    level (§8/§9)."""
    present_types = {item.source_type for item in evidence}
    if EVIDENCE_SOURCE_FINANCIAL_STATEMENT not in present_types:
        return EVIDENCE_CONFIDENCE_FLOOR

    coverage = sum(
        weight
        for source_type, weight in _SOURCE_TYPE_WEIGHTS.items()
        if source_type in present_types
    )
    return max(0.0, min(1.0, coverage))

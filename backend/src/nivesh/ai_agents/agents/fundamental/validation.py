"""Deterministic hallucination-prevention guards for the Fundamental Analyst.

Pure functions, no I/O -- kept separate from agent.py so these
safety-critical checks are independently unit-testable, mirroring every
other module's validation.py separation. See FUNDAMENTAL_ANALYST_DESIGN.md
§9 for the full defense-in-depth rationale; this module implements the
deterministic, zero-LLM-cost layers:

- A hard, pattern-based investment-advice-language filter -- the single
  most important guard given this platform's "research only, never
  trades" identity (PROJECT_CONTEXT.md §1). Fails closed and does not
  depend on the model "remembering" the system prompt's instruction.
- Citation-index range validation and unsupported-claim dropping.
- A deterministic evidence-coverage confidence signal that the model's
  own self-reported confidence can only lower, never raise.
"""

import re
from collections.abc import Sequence

from fastapi import status

from nivesh.ai_agents.agents.fundamental.schemas import CitationRef, FundamentalMetricAssessment
from nivesh.core.exceptions import NiveshError
from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_DOCUMENT_SECTION,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
    EVIDENCE_SOURCE_RESEARCH_SUMMARY,
)
from nivesh.retrieval_engine.normalization import EvidenceItem

# A finding with zero financial_statement evidence cannot meaningfully
# assess "financial fundamentals" no matter what the model claims -- this
# floor forces evidence_confidence low regardless of other evidence
# present, and agent.py short-circuits the LLM call entirely at this
# level (see FUNDAMENTAL_ANALYST_DESIGN.md §8/§9).
EVIDENCE_CONFIDENCE_FLOOR = 0.1

_SOURCE_TYPE_WEIGHTS: dict[str, float] = {
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT: 0.6,
    EVIDENCE_SOURCE_CORPORATE_FILING: 0.2,
    EVIDENCE_SOURCE_DOCUMENT_SECTION: 0.1,
    EVIDENCE_SOURCE_RESEARCH_SUMMARY: 0.1,
}

# Word-boundary, case-insensitive patterns for buy/sell/hold-style
# investment advice and price targets -- deliberately narrow (word
# boundaries) to avoid false positives such as "sales" matching "sell".
_ADVICE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bbuy\b",
        r"\bsell\b",
        r"\bshould invest\b",
        r"\brecommend(?:ed|ing)?\s+(?:purchasing|buying|selling|investing)\b",
        r"\bprice target\b",
        r"\btarget price\b",
        r"\baccumulate\b",
        r"\binvest(?:ing)? in\b",
        r"\bportfolio allocation\b",
        r"\b(?:buy|sell|hold|overweight|underweight)\s+rating\b",
        r"\bstrong buy\b",
        r"\bstrong sell\b",
    )
)


class InvestmentAdviceDetectedError(NiveshError):
    """Raised when generated output contains buy/sell/hold-style
    investment-advice language. A hard compliance rejection, not a
    warning -- fails closed rather than silently stripping the offending
    text, since this platform never gives investment advice
    (PROJECT_CONTEXT.md §1)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVESTMENT_ADVICE_DETECTED"


def check_no_investment_advice(*texts: str) -> None:
    for text in texts:
        for pattern in _ADVICE_PATTERNS:
            if pattern.search(text):
                raise InvestmentAdviceDetectedError(
                    f"Generated output matched investment-advice pattern "
                    f"{pattern.pattern!r}; rejected before persistence."
                )


def compute_evidence_confidence(evidence: Sequence[EvidenceItem]) -> float:
    """Deterministic, pre-LLM confidence signal computed purely from what
    retrieval_engine returned, before the LLM is ever called. The model's
    own self-reported confidence (see compute_confidence_score) can only
    lower this, never raise it -- see FUNDAMENTAL_ANALYST_DESIGN.md §8."""
    present_types = {item.source_type for item in evidence}
    if EVIDENCE_SOURCE_FINANCIAL_STATEMENT not in present_types:
        return EVIDENCE_CONFIDENCE_FLOOR

    coverage = sum(
        weight
        for source_type, weight in _SOURCE_TYPE_WEIGHTS.items()
        if source_type in present_types
    )
    return max(0.0, min(1.0, coverage))


def compute_confidence_score(evidence_confidence: float, llm_confidence: float) -> float:
    """Final confidence is never higher than the deterministic
    evidence-coverage signal, regardless of what the model reports -- a
    deliberate simplification (min, not a weighted blend), documented as
    a first-version choice to revisit once real output exists to tune
    against (§8)."""
    bounded_llm_confidence = max(0.0, min(1.0, llm_confidence))
    return min(evidence_confidence, bounded_llm_confidence)


def filter_valid_citation_refs(refs: Sequence[int], evidence_count: int) -> list[int]:
    return [idx for idx in refs if 1 <= idx <= evidence_count]


def drop_unsupported_assessments(
    assessments: Sequence[FundamentalMetricAssessment], evidence_count: int
) -> tuple[list[FundamentalMetricAssessment], int]:
    """Drops any assessment whose citation_refs resolve to zero real
    evidence items once out-of-range indices are filtered out -- a
    zero-cost, fully deterministic guard against both a hallucinated
    citation index and an empty citation list (§7/§9). Returns the
    surviving assessments (with their citation_refs narrowed to only the
    valid indices) plus how many were dropped entirely."""
    kept: list[FundamentalMetricAssessment] = []
    dropped = 0
    for assessment in assessments:
        valid_refs = filter_valid_citation_refs(assessment.citation_refs, evidence_count)
        if not valid_refs:
            dropped += 1
            continue
        kept.append(assessment.model_copy(update={"citation_refs": valid_refs}))
    return kept, dropped


def resolve_citation_refs(
    assessments: Sequence[FundamentalMetricAssessment], evidence: Sequence[EvidenceItem]
) -> list[CitationRef]:
    """Resolves every citation index actually used across the surviving
    assessments back to the underlying EvidenceItem identity, in index
    order. Assumes indices have already been range-validated by
    drop_unsupported_assessments."""
    used_indices = sorted({idx for assessment in assessments for idx in assessment.citation_refs})
    return [
        CitationRef(
            index=idx,
            source_type=evidence[idx - 1].source_type,
            source_table=evidence[idx - 1].source_table,
            source_id=evidence[idx - 1].source_id,
            title=evidence[idx - 1].title,
            evidence_date=evidence[idx - 1].evidence_date,
        )
        for idx in used_indices
    ]

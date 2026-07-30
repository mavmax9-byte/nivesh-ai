"""Shared hallucination-prevention guardrails for every ai_agents specialist,
the Committee Chair, and Compliance.

Promoted out of `agents/fundamental/validation.py` during the v1.0 Investment
Committee build (INVESTMENT_COMMITTEE_DESIGN.md §4): nothing about citation-
range validation, unsupported-claim dropping, or the investment-advice-
language filter was ever Fundamental-specific -- every new specialist, the
Chair (one level up, over its own globally-renumbered citation list, §7), and
Compliance (re-running the advice filter over the Chair's synthesized text,
§6) all share the exact same rules. Pure functions, no I/O, mirroring every
other module's validation.py separation. Zero behavior change from v0.9 for
the functions that moved here -- `agents/fundamental/validation.py` now
imports them from this module instead of defining them.

`agents/fundamental/validation.py` keeps `compute_evidence_confidence` and
its `_SOURCE_TYPE_WEIGHTS` -- that logic is genuinely Fundamental-specific
(which evidence types matter and how much), not generic, so each specialist
is expected to define its own version the same way. `compute_confidence_score`
(the final `min(evidence_confidence, bounded(llm_confidence))` blend) *is*
promoted here, even though the design doc's §4 list didn't name it
explicitly: it is already fully generic (two floats in, one float out) and
every specialist -- old and new -- needs the identical blend, so duplicating
it four more times would be pure copy-paste with no domain-specific content.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any, Literal, Protocol, TypeVar, cast

from fastapi import status
from pydantic import BaseModel, ConfigDict

from nivesh.core.exceptions import NiveshError
from nivesh.retrieval_engine.normalization import EvidenceItem

# A finding with zero evidence at all cannot meaningfully assess anything no
# matter what the model claims -- every specialist's own evidence-confidence
# function is expected to return (at most) this floor when its own required
# evidence types are entirely absent, and to short-circuit the LLM call
# entirely at that point (see agents/fundamental/agent.py for the precedent
# every new specialist follows).
EVIDENCE_CONFIDENCE_FLOOR = 0.1

Stance = Literal["positive", "negative", "neutral"]

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
    (PROJECT_CONTEXT.md §1). Raised both at the individual-specialist level
    (agent.py) and at the committee level (Compliance's re-check of the
    Chair's synthesized text, see committee/compliance.py)."""

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


def compute_confidence_score(evidence_confidence: float, llm_confidence: float) -> float:
    """Final confidence is never higher than the deterministic
    evidence-coverage signal, regardless of what the model reports -- a
    deliberate simplification (min, not a weighted blend), documented as a
    first-version choice to revisit once real output exists to tune against
    (FUNDAMENTAL_ANALYST_DESIGN.md §8)."""
    bounded_llm_confidence = max(0.0, min(1.0, llm_confidence))
    return min(evidence_confidence, bounded_llm_confidence)


def filter_valid_citation_refs(refs: Sequence[int], evidence_count: int) -> list[int]:
    return [idx for idx in refs if 1 <= idx <= evidence_count]


class CitationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str
    evidence_date: date | None


class SpecialistAssessment(BaseModel):
    """The shared per-claim shape every *new* v1.0 specialist (Technical,
    Valuation, News & Sentiment, Risk) returns -- `stance` replaces
    Fundamental's separate `strengths`/`concerns` lists with one list plus a
    classification field (INVESTMENT_COMMITTEE_DESIGN.md §4). Fundamental
    Analyst's own already-shipped `FundamentalMetricAssessment` is left
    exactly as it is; the Chair normalizes both shapes when synthesizing
    (see committee/chair.py)."""

    metric: str
    observation: str
    stance: Stance
    citation_refs: list[int]


class _HasCitationRefs(Protocol):
    citation_refs: list[int]


class _CitedAssessment(_HasCitationRefs, Protocol):
    def model_copy(self, *, update: dict[str, Any]) -> "_CitedAssessment": ...


AssessmentT = TypeVar("AssessmentT", bound=_CitedAssessment)


def drop_unsupported_assessments(  # noqa: UP047 -- keep runnable under Python 3.11 tooling
    assessments: Sequence[AssessmentT], evidence_count: int
) -> tuple[list[AssessmentT], int]:
    """Drops any assessment whose citation_refs resolve to zero real
    evidence items once out-of-range indices are filtered out -- a
    zero-cost, fully deterministic guard against both a hallucinated
    citation index and an empty citation list. Returns the surviving
    assessments (with their citation_refs narrowed to only the valid
    indices) plus how many were dropped entirely. Generic over any
    assessment shape with a `citation_refs: list[int]` field and a
    pydantic `model_copy` -- both `FundamentalMetricAssessment` and
    `SpecialistAssessment` satisfy this."""
    kept: list[AssessmentT] = []
    dropped = 0
    for assessment in assessments:
        valid_refs = filter_valid_citation_refs(assessment.citation_refs, evidence_count)
        if not valid_refs:
            dropped += 1
            continue
        updated = assessment.model_copy(update={"citation_refs": valid_refs})
        kept.append(cast(AssessmentT, updated))
    return kept, dropped


def resolve_citation_refs(
    assessments: Sequence[_HasCitationRefs], evidence: Sequence[EvidenceItem]
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

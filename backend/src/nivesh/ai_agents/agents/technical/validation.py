"""Technical-Analyst-specific evidence-confidence weighting.

Unlike Fundamental Analyst's multi-source-type weighted coverage
(`fundamental/validation.py`), Technical Analyst has exactly one possible
evidence source (`technical_indicator` -- see queries.py), so its
evidence-confidence signal is necessarily binary: either the company's
latest technical indicator snapshot is present, or it isn't. There is no
"partial coverage" state to reward the way Fundamental rewards having more
of five possible source types.
"""

from collections.abc import Sequence

from nivesh.ai_agents.agents.technical.queries import RELEVANT_EVIDENCE_TYPES
from nivesh.ai_agents.guardrails import EVIDENCE_CONFIDENCE_FLOOR
from nivesh.retrieval_engine.normalization import EvidenceItem

# No coverage gradient is possible with a single source type, so this is a
# fixed value, not a weighted sum -- documented as a starting choice, not
# empirically tuned, the same caveat every other confidence constant in
# this codebase carries.
TECHNICAL_EVIDENCE_CONFIDENCE = 0.9


def compute_evidence_confidence(evidence: Sequence[EvidenceItem]) -> float:
    present_types = {item.source_type for item in evidence}
    if not present_types & RELEVANT_EVIDENCE_TYPES:
        return EVIDENCE_CONFIDENCE_FLOOR
    return TECHNICAL_EVIDENCE_CONFIDENCE

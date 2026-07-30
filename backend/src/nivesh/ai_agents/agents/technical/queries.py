"""Deterministic retrieval inputs for the Technical Analyst.

`TECHNICAL_ANALYSIS_QUERY` mirrors `fundamental/queries.py`'s
`FUNDAMENTAL_ANALYSIS_QUERY` -- a fixed, versioned, non-parameterized query
(see that module's own docstring for why). `RELEVANT_EVIDENCE_TYPES` is
`technical_indicator` only (INVESTMENT_COMMITTEE_DESIGN.md §3) --
`retrieval_engine`'s own `_technical_evidence` (v0.8) already bundles every
indicator value into one evidence item per company, so this specialist will
almost always have exactly one citable evidence item; that is correct, not
a bug (design doc §3's "two honest gaps" note).
"""

from nivesh.retrieval_engine.models import EVIDENCE_SOURCE_TECHNICAL_INDICATOR

TECHNICAL_ANALYSIS_QUERY = (
    "trend direction, momentum, volatility, and volume behavior from technical indicators"
)

RELEVANT_EVIDENCE_TYPES = frozenset({EVIDENCE_SOURCE_TECHNICAL_INDICATOR})

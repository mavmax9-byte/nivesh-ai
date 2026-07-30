"""Deterministic retrieval inputs for the Valuation Analyst.

Mirrors `fundamental/queries.py`'s `FUNDAMENTAL_ANALYSIS_QUERY` shape.
`RELEVANT_EVIDENCE_TYPES` is `financial_statement` + `corporate_filing`
(INVESTMENT_COMMITTEE_DESIGN.md §3) -- the same evidence this agent's own
`ratios.py` step separately draws a specific statement from to compute a
real P/E ratio, appended as one additional synthetic evidence item before
prompt assembly (see agent.py).
"""

from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
)

VALUATION_ANALYSIS_QUERY = (
    "earnings, book value, valuation ratios, and whether the company's fundamentals are "
    "reasonably reflected in available valuation-relevant evidence"
)

RELEVANT_EVIDENCE_TYPES = frozenset(
    {EVIDENCE_SOURCE_FINANCIAL_STATEMENT, EVIDENCE_SOURCE_CORPORATE_FILING}
)

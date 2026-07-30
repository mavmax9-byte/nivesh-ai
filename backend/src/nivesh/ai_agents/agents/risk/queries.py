"""Deterministic retrieval inputs for the Risk Analyst.

`RELEVANT_EVIDENCE_TYPES` is `financial_statement` + `document_section` +
`corporate_filing` (INVESTMENT_COMMITTEE_DESIGN.md §3) -- leverage/
liquidity signals from financial statements, explicit "Risk Factors"
sections from filing document extractions (these already exist as real
extracted data, headed things like "Risk Factors"), and the filings
themselves for context.
"""

from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_DOCUMENT_SECTION,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
)

RISK_ANALYSIS_QUERY = (
    "leverage, liquidity, disclosed risk factors, and volatility-relevant financial condition"
)

RELEVANT_EVIDENCE_TYPES = frozenset(
    {
        EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
        EVIDENCE_SOURCE_DOCUMENT_SECTION,
        EVIDENCE_SOURCE_CORPORATE_FILING,
    }
)

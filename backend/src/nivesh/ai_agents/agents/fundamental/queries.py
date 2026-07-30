"""Deterministic retrieval inputs for the Fundamental Analyst.

`FUNDAMENTAL_ANALYSIS_QUERY` is a fixed constant, not a free-text user
query -- `AgentContext` (agents/base.py) carries no search string, and a
canonical, versioned query keeps every run reproducible (see
FUNDAMENTAL_ANALYST_DESIGN.md §2). It is not tuned or parameterized per
company/sector in this version -- that would be speculative without real
usage data, the same reasoning PROJECT_CONTEXT.md §12 item 3 already
applies to deferring cross-provider news dedup.

`RELEVANT_EVIDENCE_TYPES` is the client-side filter applied to whatever
`retrieval_engine.build_context_package` returns. `technical_indicator`
and `news_article` evidence belongs to other, not-yet-built specialist
agents (a future Technical Analyst, News/Sentiment Analyst), not this
one. Filtering here -- rather than asking `retrieval_engine` to filter --
keeps `retrieval_engine`'s contract generic and requires zero changes to
that module (§3/§12): every future agent is expected to define its own
query + evidence-type-allowlist pair the same way.
"""

from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_COMPANY_PROFILE,
    EVIDENCE_SOURCE_CORPORATE_FILING,
    EVIDENCE_SOURCE_DOCUMENT_SECTION,
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
    EVIDENCE_SOURCE_RESEARCH_SUMMARY,
)

FUNDAMENTAL_ANALYSIS_QUERY = (
    "revenue growth, profitability, margins, balance sheet strength, "
    "debt levels, cash flow, valuation ratios, and overall financial health"
)

RELEVANT_EVIDENCE_TYPES = frozenset(
    {
        EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
        EVIDENCE_SOURCE_CORPORATE_FILING,
        EVIDENCE_SOURCE_DOCUMENT_SECTION,
        EVIDENCE_SOURCE_RESEARCH_SUMMARY,
        EVIDENCE_SOURCE_COMPANY_PROFILE,
    }
)

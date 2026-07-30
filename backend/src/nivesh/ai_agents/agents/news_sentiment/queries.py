"""Deterministic retrieval inputs for the News & Sentiment Analyst.

Pre-approved for `ai_agents` explicitly during v0.9 planning
(PROJECT_CONTEXT.md §12 item 1: "News sentiment analysis... belong here,
not in `news_intelligence`"). `RELEVANT_EVIDENCE_TYPES` is `news_article` +
`research_summary` (INVESTMENT_COMMITTEE_DESIGN.md §3).
"""

from nivesh.retrieval_engine.models import (
    EVIDENCE_SOURCE_NEWS_ARTICLE,
    EVIDENCE_SOURCE_RESEARCH_SUMMARY,
)

NEWS_SENTIMENT_ANALYSIS_QUERY = (
    "recent news coverage, disclosed corporate developments, and their tone and substance"
)

RELEVANT_EVIDENCE_TYPES = frozenset(
    {EVIDENCE_SOURCE_NEWS_ARTICLE, EVIDENCE_SOURCE_RESEARCH_SUMMARY}
)

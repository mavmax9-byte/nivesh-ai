"""News & Sentiment-Analyst-specific evidence-confidence weighting.

Binary, like Technical Analyst's (`technical/validation.py`): both relevant
evidence types (news_article, research_summary) are treated as
interchangeable substance for sentiment purposes, so there is no
meaningfully different weighting between them the way Fundamental's five
source types warrant.
"""

from collections.abc import Sequence

from nivesh.ai_agents.agents.news_sentiment.queries import RELEVANT_EVIDENCE_TYPES
from nivesh.ai_agents.guardrails import EVIDENCE_CONFIDENCE_FLOOR
from nivesh.retrieval_engine.normalization import EvidenceItem

# No coverage gradient distinguishes news_article from research_summary for
# sentiment purposes -- documented starting choice, not empirically tuned.
NEWS_SENTIMENT_EVIDENCE_CONFIDENCE = 0.8


def compute_evidence_confidence(evidence: Sequence[EvidenceItem]) -> float:
    present_types = {item.source_type for item in evidence}
    if not present_types & RELEVANT_EVIDENCE_TYPES:
        return EVIDENCE_CONFIDENCE_FLOOR
    return NEWS_SENTIMENT_EVIDENCE_CONFIDENCE

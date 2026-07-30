from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.news_sentiment.validation import (
    NEWS_SENTIMENT_EVIDENCE_CONFIDENCE,
    compute_evidence_confidence,
)
from nivesh.ai_agents.guardrails import EVIDENCE_CONFIDENCE_FLOOR
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(source_type: str) -> EvidenceItem:
    return EvidenceItem(
        source_type=source_type,
        source_table="x",
        source_id=uuid4(),
        title="Title",
        snippet="Snippet",
        evidence_date=date(2026, 7, 1),
        relevance_score=0.5,
        retrieved_via=("structured",),
    )


def test_compute_evidence_confidence_floors_without_relevant_evidence():
    assert (
        compute_evidence_confidence([_evidence_item("financial_statement")])
        == EVIDENCE_CONFIDENCE_FLOOR
    )


def test_compute_evidence_confidence_is_fixed_when_news_present():
    assert (
        compute_evidence_confidence([_evidence_item("news_article")])
        == NEWS_SENTIMENT_EVIDENCE_CONFIDENCE
    )


def test_compute_evidence_confidence_is_fixed_when_research_summary_present():
    assert (
        compute_evidence_confidence([_evidence_item("research_summary")])
        == NEWS_SENTIMENT_EVIDENCE_CONFIDENCE
    )

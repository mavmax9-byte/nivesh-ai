from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.technical.validation import (
    TECHNICAL_EVIDENCE_CONFIDENCE,
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


def test_compute_evidence_confidence_floors_without_technical_indicator():
    assert (
        compute_evidence_confidence([_evidence_item("news_article")]) == EVIDENCE_CONFIDENCE_FLOOR
    )


def test_compute_evidence_confidence_is_fixed_when_indicator_present():
    assert (
        compute_evidence_confidence([_evidence_item("technical_indicator")])
        == TECHNICAL_EVIDENCE_CONFIDENCE
    )


def test_compute_evidence_confidence_floors_on_empty_evidence():
    assert compute_evidence_confidence([]) == EVIDENCE_CONFIDENCE_FLOOR

from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.risk.validation import compute_evidence_confidence
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
        compute_evidence_confidence([_evidence_item("news_article")]) == EVIDENCE_CONFIDENCE_FLOOR
    )


def test_compute_evidence_confidence_rewards_document_section_presence():
    confidence = compute_evidence_confidence([_evidence_item("document_section")])
    assert confidence > EVIDENCE_CONFIDENCE_FLOOR


def test_compute_evidence_confidence_increases_with_more_source_types():
    single = compute_evidence_confidence([_evidence_item("financial_statement")])
    combined = compute_evidence_confidence(
        [_evidence_item("financial_statement"), _evidence_item("document_section")]
    )
    assert combined > single


def test_compute_evidence_confidence_never_exceeds_one():
    evidence = [
        _evidence_item("financial_statement"),
        _evidence_item("document_section"),
        _evidence_item("corporate_filing"),
    ]
    assert compute_evidence_confidence(evidence) <= 1.0

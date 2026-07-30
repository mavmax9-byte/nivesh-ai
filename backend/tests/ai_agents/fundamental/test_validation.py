from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.fundamental.validation import (
    EVIDENCE_CONFIDENCE_FLOOR,
    compute_evidence_confidence,
)
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(source_type: str, **overrides) -> EvidenceItem:
    defaults = dict(
        source_type=source_type,
        source_table="x",
        source_id=uuid4(),
        title="Title",
        snippet="Snippet",
        evidence_date=date(2026, 7, 1),
        relevance_score=0.5,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


# -- compute_evidence_confidence ---------------------------------------


def test_compute_evidence_confidence_floors_without_financial_statement():
    evidence = [_evidence_item("news_article"), _evidence_item("corporate_filing")]
    assert compute_evidence_confidence(evidence) == EVIDENCE_CONFIDENCE_FLOOR


def test_compute_evidence_confidence_rewards_financial_statement_presence():
    evidence = [_evidence_item("financial_statement")]
    confidence = compute_evidence_confidence(evidence)
    assert confidence > EVIDENCE_CONFIDENCE_FLOOR


def test_compute_evidence_confidence_increases_with_more_source_types():
    financial_only = compute_evidence_confidence([_evidence_item("financial_statement")])
    financial_and_filing = compute_evidence_confidence(
        [_evidence_item("financial_statement"), _evidence_item("corporate_filing")]
    )
    assert financial_and_filing > financial_only


def test_compute_evidence_confidence_never_exceeds_one():
    evidence = [
        _evidence_item("financial_statement"),
        _evidence_item("corporate_filing"),
        _evidence_item("document_section"),
        _evidence_item("research_summary"),
    ]
    assert compute_evidence_confidence(evidence) <= 1.0

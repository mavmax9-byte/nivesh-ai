from datetime import date
from uuid import uuid4

import pytest

from nivesh.ai_agents.agents.fundamental.schemas import FundamentalMetricAssessment
from nivesh.ai_agents.guardrails import (
    InvestmentAdviceDetectedError,
    SpecialistAssessment,
    check_no_investment_advice,
    compute_confidence_score,
    drop_unsupported_assessments,
    filter_valid_citation_refs,
    resolve_citation_refs,
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


# -- check_no_investment_advice ---------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Investors should buy this stock now.",
        "We recommend selling the position.",
        "Our price target is INR 4500.",
        "This stock has a strong buy rating.",
        "Consider accumulate over the next quarter.",
    ],
)
def test_check_no_investment_advice_rejects_advice_language(text):
    with pytest.raises(InvestmentAdviceDetectedError):
        check_no_investment_advice(text)


@pytest.mark.parametrize(
    "text",
    [
        "Revenue grew 12% year over year, per the Q1 filing.",
        "Total sales increased across all segments.",
        "The company's cash flow remained stable.",
    ],
)
def test_check_no_investment_advice_allows_neutral_research_language(text):
    check_no_investment_advice(text)  # should not raise


# -- compute_confidence_score -------------------------------------------


def test_compute_confidence_score_is_capped_by_evidence_confidence():
    assert compute_confidence_score(evidence_confidence=0.3, llm_confidence=0.9) == 0.3


def test_compute_confidence_score_is_capped_by_llm_confidence():
    assert compute_confidence_score(evidence_confidence=0.9, llm_confidence=0.2) == 0.2


def test_compute_confidence_score_clamps_out_of_range_llm_confidence():
    assert compute_confidence_score(evidence_confidence=0.5, llm_confidence=5.0) == 0.5
    assert compute_confidence_score(evidence_confidence=0.5, llm_confidence=-1.0) == 0.0


# -- filter_valid_citation_refs / drop_unsupported_assessments ----------


def test_filter_valid_citation_refs_drops_out_of_range_indices():
    assert filter_valid_citation_refs([1, 2, 5, 0, -1], evidence_count=3) == [1, 2]


def test_drop_unsupported_assessments_keeps_assessments_with_valid_refs():
    assessments = [
        FundamentalMetricAssessment(metric="revenue", observation="grew", citation_refs=[1]),
        FundamentalMetricAssessment(metric="margin", observation="stable", citation_refs=[2, 9]),
    ]
    kept, dropped = drop_unsupported_assessments(assessments, evidence_count=2)
    assert dropped == 0
    assert len(kept) == 2
    assert kept[1].citation_refs == [2]  # index 9 filtered out, 2 survives


def test_drop_unsupported_assessments_drops_assessments_with_zero_valid_refs():
    assessments = [
        FundamentalMetricAssessment(metric="revenue", observation="grew", citation_refs=[1]),
        FundamentalMetricAssessment(
            metric="hallucinated", observation="made up", citation_refs=[99]
        ),
        FundamentalMetricAssessment(metric="empty", observation="no citation", citation_refs=[]),
    ]
    kept, dropped = drop_unsupported_assessments(assessments, evidence_count=1)
    assert dropped == 2
    assert len(kept) == 1
    assert kept[0].metric == "revenue"


def test_drop_unsupported_assessments_works_generically_over_specialist_assessment():
    """Confirms the promoted function is truly generic, not accidentally
    still coupled to FundamentalMetricAssessment -- SpecialistAssessment
    (the new v1.0 shared shape, ai_agents/guardrails.py) has an extra
    `stance` field and must survive model_copy the same way."""
    assessments = [
        SpecialistAssessment(
            metric="momentum", observation="RSI is elevated", stance="positive", citation_refs=[1]
        ),
        SpecialistAssessment(
            metric="hallucinated", observation="made up", stance="neutral", citation_refs=[99]
        ),
    ]
    kept, dropped = drop_unsupported_assessments(assessments, evidence_count=1)
    assert dropped == 1
    assert len(kept) == 1
    assert kept[0].stance == "positive"


# -- resolve_citation_refs -----------------------------------------------


def test_resolve_citation_refs_maps_indices_to_evidence_identity():
    evidence = [
        _evidence_item("financial_statement", title="Statement"),
        _evidence_item("corporate_filing", title="Filing"),
    ]
    assessments = [
        FundamentalMetricAssessment(metric="revenue", observation="grew", citation_refs=[1]),
        FundamentalMetricAssessment(metric="margin", observation="stable", citation_refs=[1, 2]),
    ]
    citations = resolve_citation_refs(assessments, evidence)

    assert [c.index for c in citations] == [1, 2]
    assert citations[0].source_id == evidence[0].source_id
    assert citations[0].title == "Statement"
    assert citations[1].source_id == evidence[1].source_id
    assert citations[1].title == "Filing"

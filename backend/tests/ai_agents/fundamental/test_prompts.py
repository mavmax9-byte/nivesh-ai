from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.fundamental.prompts import (
    FUNDAMENTAL_ANALYST_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_user_prompt,
)
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(**overrides) -> EvidenceItem:
    defaults = dict(
        source_type="financial_statement",
        source_table="financial_statements",
        source_id=uuid4(),
        title="Q1 FY26 statement",
        snippet="Revenue: 1000, Net income: 200.",
        evidence_date=date(2026, 6, 30),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def test_system_prompt_forbids_investment_advice_and_requires_citations():
    assert "ADVICE" in FUNDAMENTAL_ANALYST_SYSTEM_PROMPT
    assert "citation_refs" in FUNDAMENTAL_ANALYST_SYSTEM_PROMPT
    assert "JSON" in FUNDAMENTAL_ANALYST_SYSTEM_PROMPT


def test_prompt_version_is_a_fixed_string():
    assert PROMPT_VERSION == "fundamental-v1"


def test_build_user_prompt_includes_symbol_and_evidence_citations():
    evidence = [_evidence_item()]
    prompt = build_user_prompt("TCS", "revenue growth", evidence)

    assert "TCS" in prompt
    assert "[1]" in prompt
    assert "Q1 FY26 statement" in prompt


def test_build_user_prompt_indices_match_filtered_evidence_order():
    evidence = [
        _evidence_item(title="First item"),
        _evidence_item(title="Second item"),
    ]
    prompt = build_user_prompt("TCS", "revenue growth", evidence)

    first_index = prompt.index("[1]")
    second_index = prompt.index("[2]")
    assert prompt.index("First item") > first_index
    assert prompt.index("Second item") > second_index
    assert first_index < second_index

from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.valuation.prompts import (
    PROMPT_VERSION,
    VALUATION_ANALYST_SYSTEM_PROMPT,
    build_user_prompt,
)
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(**overrides) -> EvidenceItem:
    defaults = dict(
        source_type="financial_statement",
        source_table="financial_statements",
        source_id=uuid4(),
        title="Q1 FY26 statement",
        snippet="EPS: 10.00",
        evidence_date=date(2026, 6, 30),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def test_system_prompt_forbids_investment_advice_and_requires_citations():
    assert "ADVICE" in VALUATION_ANALYST_SYSTEM_PROMPT
    assert "citation_refs" in VALUATION_ANALYST_SYSTEM_PROMPT
    assert "JSON" in VALUATION_ANALYST_SYSTEM_PROMPT


def test_prompt_version_is_a_fixed_string():
    assert PROMPT_VERSION == "valuation-v1"


def test_build_user_prompt_includes_symbol_and_evidence_citations():
    prompt = build_user_prompt("TCS", "valuation", [_evidence_item()])
    assert "TCS" in prompt
    assert "[1]" in prompt
    assert "Q1 FY26 statement" in prompt

from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.risk.prompts import (
    PROMPT_VERSION,
    RISK_ANALYST_SYSTEM_PROMPT,
    build_user_prompt,
)
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(**overrides) -> EvidenceItem:
    defaults = dict(
        source_type="document_section",
        source_table="document_sections",
        source_id=uuid4(),
        title="Risk Factors",
        snippet="The company is exposed to currency risk.",
        evidence_date=date(2026, 7, 1),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def test_system_prompt_forbids_investment_advice_and_requires_citations():
    assert "ADVICE" in RISK_ANALYST_SYSTEM_PROMPT
    assert "citation_refs" in RISK_ANALYST_SYSTEM_PROMPT
    assert "JSON" in RISK_ANALYST_SYSTEM_PROMPT


def test_prompt_version_is_a_fixed_string():
    assert PROMPT_VERSION == "risk-v1.3"


def test_build_user_prompt_includes_symbol_and_evidence_citations():
    prompt = build_user_prompt("TCS", "risk factors", [_evidence_item()])
    assert "TCS" in prompt
    assert "[1]" in prompt
    assert "Risk Factors" in prompt

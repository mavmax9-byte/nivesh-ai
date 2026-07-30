from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.technical.prompts import (
    PROMPT_VERSION,
    TECHNICAL_ANALYST_SYSTEM_PROMPT,
    build_user_prompt,
)
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(**overrides) -> EvidenceItem:
    defaults = dict(
        source_type="technical_indicator",
        source_table="technical_indicators",
        source_id=uuid4(),
        title="Latest technical indicator snapshot",
        snippet="RSI=55.0",
        evidence_date=date(2026, 7, 1),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def test_system_prompt_forbids_investment_advice_and_requires_citations():
    assert "ADVICE" in TECHNICAL_ANALYST_SYSTEM_PROMPT
    assert "citation_refs" in TECHNICAL_ANALYST_SYSTEM_PROMPT
    assert "JSON" in TECHNICAL_ANALYST_SYSTEM_PROMPT


def test_prompt_version_is_a_fixed_string():
    assert PROMPT_VERSION == "technical-v1"


def test_build_user_prompt_includes_symbol_and_evidence_citations():
    prompt = build_user_prompt("TCS", "trend and momentum", [_evidence_item()])
    assert "TCS" in prompt
    assert "[1]" in prompt
    assert "Latest technical indicator snapshot" in prompt

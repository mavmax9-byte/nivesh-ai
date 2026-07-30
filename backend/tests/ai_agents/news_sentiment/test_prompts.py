from datetime import date
from uuid import uuid4

from nivesh.ai_agents.agents.news_sentiment.prompts import (
    NEWS_SENTIMENT_ANALYST_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_user_prompt,
)
from nivesh.retrieval_engine.normalization import EvidenceItem


def _evidence_item(**overrides) -> EvidenceItem:
    defaults = dict(
        source_type="news_article",
        source_table="news_articles",
        source_id=uuid4(),
        title="Contract win reported",
        snippet="The company reported a new contract.",
        evidence_date=date(2026, 7, 1),
        relevance_score=0.9,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def test_system_prompt_forbids_investment_advice_and_requires_citations():
    assert "ADVICE" in NEWS_SENTIMENT_ANALYST_SYSTEM_PROMPT
    assert "citation_refs" in NEWS_SENTIMENT_ANALYST_SYSTEM_PROMPT
    assert "JSON" in NEWS_SENTIMENT_ANALYST_SYSTEM_PROMPT


def test_prompt_version_is_a_fixed_string():
    assert PROMPT_VERSION == "news-sentiment-v1"


def test_build_user_prompt_includes_symbol_and_evidence_citations():
    prompt = build_user_prompt("TCS", "recent news sentiment", [_evidence_item()])
    assert "TCS" in prompt
    assert "[1]" in prompt
    assert "Contract win reported" in prompt

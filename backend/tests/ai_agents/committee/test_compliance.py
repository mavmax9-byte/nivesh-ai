import uuid
from datetime import UTC, datetime

from nivesh.ai_agents.committee import compliance
from nivesh.ai_agents.committee.citations import CommitteeCitationRef
from nivesh.ai_agents.committee.schemas import (
    AgentDisagreement,
    CommitteeDecision,
    CommitteeThemeFinding,
    DisagreementPosition,
)


def _citation() -> CommitteeCitationRef:
    return CommitteeCitationRef(
        global_index=1,
        source_agent_codes=("fundamental_analyst",),
        source_type="financial_statement",
        source_table="financial_statements",
        source_id=uuid.uuid4(),
        title="Q1 FY26 statement",
        evidence_date=None,
    )


def _decision(**overrides) -> CommitteeDecision:
    defaults = dict(
        company_symbol="TCS",
        summary="Overall the company shows steady fundamentals.",
        findings=[
            CommitteeThemeFinding(
                theme="growth",
                observation="Revenue growth is steady.",
                stance="positive",
                citation_refs=[1],
            )
        ],
        disagreements=[],
        confidence_score=0.7,
        citations=[_citation()],
        caveats=[],
        source_findings=[],
        failed_specialists=[],
        prompt_version="committee-chair-v1",
        model_used="gpt-4o-mini",
        generated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return CommitteeDecision(**defaults)


def test_review_approves_clean_decision():
    verdict = compliance.review(_decision())
    assert verdict.approved is True
    assert verdict.reasons == []


def test_review_rejects_investment_advice_in_summary():
    verdict = compliance.review(_decision(summary="Investors should buy this stock now."))
    assert verdict.approved is False
    assert any("advice" in reason.lower() for reason in verdict.reasons)


def test_review_rejects_investment_advice_in_finding_observation():
    decision = _decision(
        findings=[
            CommitteeThemeFinding(
                theme="growth",
                observation="This is a strong buy.",
                stance="positive",
                citation_refs=[1],
            )
        ]
    )
    verdict = compliance.review(decision)
    assert verdict.approved is False


def test_review_rejects_investment_advice_in_disagreement_position():
    decision = _decision(
        disagreements=[
            AgentDisagreement(
                topic="outlook",
                positions=[
                    DisagreementPosition(
                        agent_code="fundamental_analyst",
                        stance="positive",
                        summary="Investors should accumulate this stock.",
                        citation_refs=[1],
                    )
                ],
            )
        ]
    )
    verdict = compliance.review(decision)
    assert verdict.approved is False


def test_review_rejects_untraceable_citation_refs():
    decision = _decision(citations=[])  # zero global citations, but finding cites [1]
    verdict = compliance.review(decision)
    assert verdict.approved is False
    assert any("outside the committee's own" in reason for reason in verdict.reasons)

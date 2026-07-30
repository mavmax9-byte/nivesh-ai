import uuid
from unittest.mock import AsyncMock

import pytest

from nivesh.ai_agents.committee.chair import CommitteeChair
from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.providers.base import LLMCompletion
from nivesh.ai_agents.providers.exceptions import LLMResponseParsingError


def _citation(index: int, source_id: uuid.UUID) -> dict:
    return {
        "index": index,
        "source_type": "financial_statement",
        "source_table": "financial_statements",
        "source_id": str(source_id),
        "title": f"Statement {index}",
        "evidence_date": "2026-06-30",
    }


def _fundamental_input() -> SpecialistFindingInput:
    source_id = uuid.uuid4()
    return SpecialistFindingInput(
        agent_code="fundamental_analyst",
        finding_id=uuid.uuid4(),
        confidence_score=0.7,
        evidence_sufficiency="sufficient",
        result_json={
            "summary": "Revenue grew steadily.",
            "financial_health_assessment": "Balance sheet is stable.",
            "strengths": [
                {"metric": "revenue", "observation": "Revenue grew", "citation_refs": [1]}
            ],
            "concerns": [],
            "citations": [_citation(1, source_id)],
        },
    )


def _llm_completion(parsed_json: dict) -> LLMCompletion:
    return LLMCompletion(
        raw_text="{}",
        parsed_json=parsed_json,
        model="gpt-4o-mini",
        prompt_tokens=200,
        completion_tokens=80,
        finish_reason="stop",
    )


def _valid_chair_output(citation_refs: list[int] | None = None) -> dict:
    return {
        "summary": "Overall the company shows steady fundamentals.",
        "findings": [
            {
                "theme": "growth",
                "observation": "Revenue growth is a consistent theme.",
                "stance": "positive",
                "citation_refs": citation_refs if citation_refs is not None else [1],
            }
        ],
        "disagreements": [],
        "llm_confidence": 0.75,
    }


@pytest.mark.asyncio
async def test_synthesize_produces_decision_with_resolved_global_citations():
    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(_valid_chair_output())
    chair = CommitteeChair(llm_provider=llm_provider)

    decision = await chair.synthesize("TCS", [_fundamental_input()], failed_specialists=[])

    assert decision.company_symbol == "TCS"
    assert len(decision.citations) == 1
    assert len(decision.findings) == 1
    assert decision.findings[0].citation_refs == [1]
    assert decision.source_findings[0].agent_code == "fundamental_analyst"
    assert decision.failed_specialists == []


@pytest.mark.asyncio
async def test_synthesize_drops_findings_citing_out_of_range_global_index():
    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(_valid_chair_output(citation_refs=[99]))
    chair = CommitteeChair(llm_provider=llm_provider)

    decision = await chair.synthesize("TCS", [_fundamental_input()], failed_specialists=[])

    assert decision.findings == []
    assert any("removed" in c for c in decision.caveats)


@pytest.mark.asyncio
async def test_synthesize_drops_disagreement_positions_citing_invalid_refs():
    output = _valid_chair_output()
    output["disagreements"] = [
        {
            "topic": "near-term outlook",
            "positions": [
                {
                    "agent_code": "fundamental_analyst",
                    "stance": "positive",
                    "summary": "Growth looks solid.",
                    "citation_refs": [1],
                },
                {
                    "agent_code": "technical_analyst",
                    "stance": "negative",
                    "summary": "Momentum is fading.",
                    "citation_refs": [99],
                },
            ],
        }
    ]
    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(output)
    chair = CommitteeChair(llm_provider=llm_provider)

    decision = await chair.synthesize("TCS", [_fundamental_input()], failed_specialists=[])

    assert len(decision.disagreements) == 1
    assert len(decision.disagreements[0].positions) == 1
    assert decision.disagreements[0].positions[0].agent_code == "fundamental_analyst"


@pytest.mark.asyncio
async def test_synthesize_notes_failed_specialists_in_caveats():
    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(_valid_chair_output())
    chair = CommitteeChair(llm_provider=llm_provider)

    decision = await chair.synthesize(
        "TCS", [_fundamental_input()], failed_specialists=["technical_analyst"]
    )

    assert decision.failed_specialists == ["technical_analyst"]
    assert any("technical_analyst" in c for c in decision.caveats)


@pytest.mark.asyncio
async def test_synthesize_raises_parsing_error_on_schema_mismatch():
    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion({"unexpected": "shape"})
    chair = CommitteeChair(llm_provider=llm_provider)

    with pytest.raises(LLMResponseParsingError):
        await chair.synthesize("TCS", [_fundamental_input()], failed_specialists=[])


@pytest.mark.asyncio
async def test_synthesize_does_not_reject_investment_advice_language():
    """The Chair step deliberately does NOT run check_no_investment_advice
    -- that is Compliance's job (§6). Confirms this by asserting advice
    language survives the Chair step without raising."""
    output = _valid_chair_output()
    output["summary"] = "Investors should buy this stock."
    llm_provider = AsyncMock()
    llm_provider.complete.return_value = _llm_completion(output)
    chair = CommitteeChair(llm_provider=llm_provider)

    decision = await chair.synthesize("TCS", [_fundamental_input()], failed_specialists=[])

    assert decision.summary == "Investors should buy this stock."

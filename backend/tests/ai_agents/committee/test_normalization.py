import uuid

from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.committee.normalization import normalize_findings


def _fundamental_input() -> SpecialistFindingInput:
    return SpecialistFindingInput(
        agent_code="fundamental_analyst",
        finding_id=uuid.uuid4(),
        confidence_score=0.7,
        evidence_sufficiency="sufficient",
        result_json={
            "strengths": [
                {"metric": "revenue", "observation": "Revenue grew", "citation_refs": [1]}
            ],
            "concerns": [
                {"metric": "margin", "observation": "Margin compressed", "citation_refs": [2]}
            ],
        },
    )


def _technical_input() -> SpecialistFindingInput:
    return SpecialistFindingInput(
        agent_code="technical_analyst",
        finding_id=uuid.uuid4(),
        confidence_score=0.6,
        evidence_sufficiency="sufficient",
        result_json={
            "findings": [
                {
                    "metric": "momentum",
                    "observation": "RSI is elevated",
                    "stance": "positive",
                    "citation_refs": [1],
                }
            ]
        },
    )


def test_normalize_findings_maps_fundamental_strengths_and_concerns_to_stance():
    local_to_global = {("fundamental_analyst", 1): 1, ("fundamental_analyst", 2): 2}
    normalized = normalize_findings([_fundamental_input()], local_to_global)

    assert len(normalized) == 2
    strengths = [n for n in normalized if n.metric == "revenue"][0]
    concerns = [n for n in normalized if n.metric == "margin"][0]
    assert strengths.stance == "positive"
    assert strengths.citation_refs == [1]
    assert concerns.stance == "negative"
    assert concerns.citation_refs == [2]


def test_normalize_findings_passes_through_new_specialist_stance():
    local_to_global = {("technical_analyst", 1): 5}
    normalized = normalize_findings([_technical_input()], local_to_global)

    assert len(normalized) == 1
    assert normalized[0].stance == "positive"
    assert normalized[0].citation_refs == [5]


def test_normalize_findings_drops_refs_with_no_global_mapping():
    local_to_global: dict = {}
    normalized = normalize_findings([_technical_input()], local_to_global)

    assert normalized[0].citation_refs == []

import uuid

from nivesh.ai_agents.committee.citations import build_global_citations
from nivesh.ai_agents.committee.inputs import SpecialistFindingInput


def _citation(index: int, source_id: uuid.UUID, source_type: str = "financial_statement") -> dict:
    return {
        "index": index,
        "source_type": source_type,
        "source_table": "financial_statements",
        "source_id": str(source_id),
        "title": f"Statement {index}",
        "evidence_date": "2026-06-30",
    }


def _finding_input(agent_code: str, citations: list[dict]) -> SpecialistFindingInput:
    return SpecialistFindingInput(
        agent_code=agent_code,
        finding_id=uuid.uuid4(),
        confidence_score=0.7,
        evidence_sufficiency="sufficient",
        result_json={"citations": citations},
    )


def test_build_global_citations_numbers_sequentially_across_specialists():
    id_a, id_b = uuid.uuid4(), uuid.uuid4()
    inputs = [
        _finding_input("fundamental_analyst", [_citation(1, id_a)]),
        _finding_input(
            "technical_analyst", [_citation(1, id_b, source_type="technical_indicator")]
        ),
    ]

    global_citations, local_to_global = build_global_citations(inputs)

    assert [c.global_index for c in global_citations] == [1, 2]
    assert local_to_global[("fundamental_analyst", 1)] == 1
    assert local_to_global[("technical_analyst", 1)] == 2


def test_build_global_citations_deduplicates_same_underlying_evidence():
    shared_id = uuid.uuid4()
    inputs = [
        _finding_input("fundamental_analyst", [_citation(1, shared_id)]),
        _finding_input("risk_analyst", [_citation(1, shared_id)]),
    ]

    global_citations, local_to_global = build_global_citations(inputs)

    assert len(global_citations) == 1
    assert global_citations[0].source_agent_codes == ("fundamental_analyst", "risk_analyst")
    assert local_to_global[("fundamental_analyst", 1)] == 1
    assert local_to_global[("risk_analyst", 1)] == 1


def test_build_global_citations_handles_no_citations():
    global_citations, local_to_global = build_global_citations(
        [_finding_input("fundamental_analyst", [])]
    )
    assert global_citations == []
    assert local_to_global == {}

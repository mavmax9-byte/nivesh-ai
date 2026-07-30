import uuid

import pytest

from nivesh.ai_agents.committee.confidence import compute_committee_confidence
from nivesh.ai_agents.committee.inputs import SpecialistFindingInput


def _specialist(confidence_score: float) -> SpecialistFindingInput:
    return SpecialistFindingInput(
        agent_code="fundamental_analyst",
        finding_id=uuid.uuid4(),
        confidence_score=confidence_score,
        evidence_sufficiency="sufficient",
        result_json={},
    )


def test_compute_committee_confidence_returns_zero_with_no_specialists():
    assert compute_committee_confidence([], chair_llm_confidence=0.9) == 0.0


def test_compute_committee_confidence_averages_specialist_scores():
    specialists = [_specialist(0.8), _specialist(0.4)]
    result = compute_committee_confidence(specialists, chair_llm_confidence=0.9)
    assert result == pytest.approx(0.6)  # mean(0.8, 0.4) = 0.6, capped by chair 0.9 -> 0.6


def test_compute_committee_confidence_is_capped_by_chair_confidence():
    specialists = [_specialist(0.9), _specialist(0.9)]
    result = compute_committee_confidence(specialists, chair_llm_confidence=0.2)
    assert result == 0.2


def test_compute_committee_confidence_never_raised_by_chair_confidence():
    specialists = [_specialist(0.3)]
    result = compute_committee_confidence(specialists, chair_llm_confidence=1.0)
    assert result == 0.3

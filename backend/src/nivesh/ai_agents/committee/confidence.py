"""Committee-level confidence aggregation (INVESTMENT_COMMITTEE_DESIGN.md §8).

Continues v0.9's core principle exactly: never purely LLM-self-reported.
`committee_confidence = min(mean(succeeded specialist confidence_scores),
bounded(chair.llm_confidence))` -- the Chair's own self-reported confidence
can only lower this, never raise it, the identical rule
`guardrails.compute_confidence_score` already enforces at the
single-specialist level. Equal weighting across specialists is the v1.0
default (not empirically tuned, same caveat as every other confidence
constant in this codebase); a specialist that itself hit its own
"insufficient evidence" floor already contributes a low number to the mean
by construction, so the aggregate naturally reflects a weak specialist
without any special-casing here.
"""

from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.guardrails import compute_confidence_score


def compute_committee_confidence(
    succeeded_specialists: list[SpecialistFindingInput], chair_llm_confidence: float
) -> float:
    if not succeeded_specialists:
        return 0.0
    mean_specialist_confidence = sum(
        specialist.confidence_score for specialist in succeeded_specialists
    ) / len(succeeded_specialists)
    return compute_confidence_score(mean_specialist_confidence, chair_llm_confidence)

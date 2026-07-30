"""Normalizes each specialist's own persisted finding shape into one common
structure the Committee Chair's prompt is built from
(INVESTMENT_COMMITTEE_DESIGN.md §4/§6).

Fundamental Analyst's already-shipped `strengths`/`concerns` two-list shape
is read as-is (never rewritten -- v0.9 compatibility is a hard constraint,
§4) and normalized to `stance="positive"`/`"negative"` respectively. Every
new v1.0 specialist's `findings` list (built on the shared
`SpecialistAssessment`, already carrying its own `stance`) passes through
unchanged. Each claim's `citation_refs` -- local to that specialist's own
evidence list -- are remapped onto the committee's global citation list via
`citations.build_global_citations`'s `local_to_global` lookup; a ref with
no corresponding global entry (should not happen, since every citation_ref
that survived a specialist's own guardrail already resolved to that
specialist's own `citations` list) is dropped defensively rather than
raising.
"""

from pydantic import BaseModel

from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.guardrails import Stance
from nivesh.ai_agents.models import AGENT_CODE_FUNDAMENTAL_ANALYST


class NormalizedAssessment(BaseModel):
    """A single specialist claim, ready for the Chair's prompt -- global
    citation indices, not the specialist's own local ones."""

    agent_code: str
    metric: str
    observation: str
    stance: Stance
    citation_refs: list[int]


def _remap(
    agent_code: str, local_refs: list[int], local_to_global: dict[tuple[str, int], int]
) -> list[int]:
    return sorted(
        {
            local_to_global[(agent_code, idx)]
            for idx in local_refs
            if (agent_code, idx) in local_to_global
        }
    )


def normalize_findings(
    inputs: list[SpecialistFindingInput],
    local_to_global: dict[tuple[str, int], int],
) -> list[NormalizedAssessment]:
    normalized: list[NormalizedAssessment] = []
    for entry in inputs:
        result = entry.result_json
        if entry.agent_code == AGENT_CODE_FUNDAMENTAL_ANALYST:
            normalized.extend(
                _normalize_group(
                    entry.agent_code, result.get("strengths", []), "positive", local_to_global
                )
            )
            normalized.extend(
                _normalize_group(
                    entry.agent_code, result.get("concerns", []), "negative", local_to_global
                )
            )
        else:
            for item in result.get("findings", []):
                normalized.append(
                    NormalizedAssessment(
                        agent_code=entry.agent_code,
                        metric=item["metric"],
                        observation=item["observation"],
                        stance=item["stance"],
                        citation_refs=_remap(
                            entry.agent_code, item["citation_refs"], local_to_global
                        ),
                    )
                )
    return normalized


def _normalize_group(
    agent_code: str,
    items: list[dict],
    stance: Stance,
    local_to_global: dict[tuple[str, int], int],
) -> list[NormalizedAssessment]:
    return [
        NormalizedAssessment(
            agent_code=agent_code,
            metric=item["metric"],
            observation=item["observation"],
            stance=stance,
            citation_refs=_remap(agent_code, item["citation_refs"], local_to_global),
        )
        for item in items
    ]

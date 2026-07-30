"""Global, cross-specialist citation list construction for the Committee
Chair (INVESTMENT_COMMITTEE_DESIGN.md §7).

Pure functions, no I/O and no LLM involvement -- built deterministically in
Python before the Chair's prompt is ever assembled. Unions every succeeded
specialist's already-resolved `citations` list (from its persisted
`result_json`), deduplicating by `(source_type, source_id)` -- the exact
same identity-based dedup idiom `retrieval_engine.normalization.
deduplicate_and_rank` already uses at the evidence-retrieval layer,
reapplied one level up at the citation layer. If two specialists both cited
the same underlying evidence row, it collapses to one global citation
entry, tagged with every agent that originally cited it.
"""

import uuid
from datetime import date

from pydantic import BaseModel

from nivesh.ai_agents.committee.inputs import SpecialistFindingInput
from nivesh.ai_agents.guardrails import CitationRef


class CommitteeCitationRef(BaseModel):
    global_index: int
    source_agent_codes: tuple[str, ...]
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str
    evidence_date: date | None


def _extract_local_citations(result_json: dict) -> list[CitationRef]:
    return [CitationRef.model_validate(entry) for entry in result_json.get("citations", [])]


def build_global_citations(
    inputs: list[SpecialistFindingInput],
) -> tuple[list[CommitteeCitationRef], dict[tuple[str, int], int]]:
    """Returns the deduplicated, globally-renumbered citation list, plus a
    lookup from `(agent_code, local_index)` to `global_index` -- used to
    remap each specialist's own claim-level `citation_refs` onto the
    global list when the Chair's prompt is built (see normalization.py).
    Encounter order (the order `inputs` is given in, expected to be
    `SPECIALIST_AGENT_CODES` order) determines global numbering, so the
    same inputs always produce the same global indices."""
    agent_codes_by_key: dict[tuple[str, uuid.UUID], list[str]] = {}
    first_citation_by_key: dict[tuple[str, uuid.UUID], CitationRef] = {}
    ordered_keys: list[tuple[str, uuid.UUID]] = []

    for entry in inputs:
        for citation in _extract_local_citations(entry.result_json):
            key = (citation.source_type, citation.source_id)
            if key not in first_citation_by_key:
                first_citation_by_key[key] = citation
                agent_codes_by_key[key] = [entry.agent_code]
                ordered_keys.append(key)
            elif entry.agent_code not in agent_codes_by_key[key]:
                agent_codes_by_key[key].append(entry.agent_code)

    global_citations = [
        CommitteeCitationRef(
            global_index=global_index,
            source_agent_codes=tuple(agent_codes_by_key[key]),
            source_type=first_citation_by_key[key].source_type,
            source_table=first_citation_by_key[key].source_table,
            source_id=first_citation_by_key[key].source_id,
            title=first_citation_by_key[key].title,
            evidence_date=first_citation_by_key[key].evidence_date,
        )
        for global_index, key in enumerate(ordered_keys, start=1)
    ]
    key_to_global = {key: index for index, key in enumerate(ordered_keys, start=1)}

    local_to_global: dict[tuple[str, int], int] = {}
    for entry in inputs:
        for citation in _extract_local_citations(entry.result_json):
            key = (citation.source_type, citation.source_id)
            local_to_global[(entry.agent_code, citation.index)] = key_to_global[key]

    return global_citations, local_to_global

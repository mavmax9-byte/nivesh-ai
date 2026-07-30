"""Committee Chair structured output and persisted-decision schemas.

Same two-layer shape as every specialist (INVESTMENT_COMMITTEE_DESIGN.md
§4/§6): `LLMCommitteeOutput` is exactly what the LLM is asked to produce;
`CommitteeDecision` is the full persisted/returned shape, with
`confidence_score` (the deterministic aggregation, §8), `citations` (the
global, deduplicated list, §7), `source_findings` (the traceability
manifest, §10), and `failed_specialists` (the disclosed-degradation list,
§9) all computed in Python, never asked of the model.

`CommitteeThemeFinding` and `DisagreementPosition` both satisfy
`guardrails._CitedAssessment` (a `citation_refs: list[int]` field plus
pydantic `model_copy`), so the Chair's own output is range-validated and
unsupported-claim-dropped by the exact same `guardrails.
drop_unsupported_assessments` every specialist already uses -- not a
parallel implementation (§7/§9).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from nivesh.ai_agents.committee.citations import CommitteeCitationRef
from nivesh.ai_agents.guardrails import Stance


class CommitteeThemeFinding(BaseModel):
    theme: str
    observation: str
    stance: Stance
    citation_refs: list[int]


class DisagreementPosition(BaseModel):
    agent_code: str
    stance: Stance
    summary: str
    citation_refs: list[int]


class AgentDisagreement(BaseModel):
    topic: str
    positions: list[DisagreementPosition]


class LLMCommitteeOutput(BaseModel):
    """The exact shape requested from the LLM via structured output."""

    summary: str
    findings: list[CommitteeThemeFinding]
    disagreements: list[AgentDisagreement]
    llm_confidence: float = Field(ge=0.0, le=1.0)


class SourceFindingRef(BaseModel):
    """One entry per specialist actually synthesized -- the traceability
    manifest INVESTMENT_COMMITTEE_DESIGN.md §10 requires, since
    `agent_findings` is upsert-only and a specialist's row can be
    overwritten by a later, unrelated run before anyone reads this
    committee decision again."""

    agent_code: str
    finding_id: uuid.UUID
    confidence_score: float
    evidence_sufficiency: str


class CommitteeDecision(BaseModel):
    company_symbol: str
    summary: str
    findings: list[CommitteeThemeFinding]
    disagreements: list[AgentDisagreement]
    confidence_score: float
    citations: list[CommitteeCitationRef]
    caveats: list[str]
    source_findings: list[SourceFindingRef]
    failed_specialists: list[str]
    prompt_version: str
    model_used: str
    generated_at: datetime

"""The Chair's own input DTO.

Decouples `citations.py`/`normalization.py`/`chair.py` (pure-ish synthesis
logic) from the `ai_agents.models.AgentFinding` ORM row -- the orchestrator
converts each succeeded specialist's persisted finding into this shape
before handing it to the Chair (INVESTMENT_COMMITTEE_DESIGN.md §6: "The
Chair never calls retrieval_engine directly... its only inputs are the
specialists' own already-persisted AgentFinding/detail payloads").
"""

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpecialistFindingInput:
    agent_code: str
    finding_id: uuid.UUID
    confidence_score: float
    evidence_sufficiency: str
    result_json: dict[str, Any]

"""AI Layer request/response schemas.

`AnalysisRequest`/`AnalysisJobStatus` follow the job-based API pattern
from docs/v1 09-API-Design.md section 9.4 -- unchanged, still the
orchestrator's own shape, still `501` until
`InvestmentCommitteeOrchestrator` exists.

The Fundamental Analyst (v0.9) is invoked directly today via a separate,
narrower route group (see router.py's `fundamental_router`) since the
orchestrator that would otherwise be its only caller doesn't exist yet
(FUNDAMENTAL_ANALYST_DESIGN.md §14). `FundamentalAnalysisGenerationResponse`
follows the standard "{symbol, status, task_id}" generate-response shape
every other `.../generate/...` route uses (mirrors
`knowledge_layer.schemas.KnowledgeGenerationResponse` exactly).
`FundamentalFindingRead` passes `result_json` through as-is (the full
`FundamentalAnalysisResult` payload agent.py already built and
validated) rather than re-declaring every nested field here, the same
"pass the already-structured payload through" choice
`KnowledgeEmbeddingRead.content_text` makes for its own blob field.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalysisRequest(BaseModel):
    company_id: uuid.UUID
    force_refresh: bool = False


class AnalysisJobStatus(BaseModel):
    job_id: uuid.UUID
    status: str


class FundamentalAnalysisGenerationResponse(BaseModel):
    symbol: str
    status: str
    task_id: str


class FundamentalFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    agent_code: str
    result_json: dict
    prompt_version: str
    model_used: str
    confidence_score: float
    evidence_sufficiency: str
    created_at: datetime
    updated_at: datetime

"""AI Layer request/response schemas.

`AnalysisRequest`/`AnalysisJobStatus` follow the job-based API pattern
from docs/v1 09-API-Design.md section 9.4 -- unchanged shape.
`POST /reports` (router.py) now really enqueues `run_investment_committee`
(v1.0) instead of raising `501`.

The Fundamental Analyst (v0.9) is invoked directly today via a separate,
narrower route group (see router.py's `fundamental_router`), and each new
v1.0 specialist (Technical, Valuation, News & Sentiment, Risk) gets its own
identically-shaped direct-invocation route group -- even with the
orchestrator now real, independent invocation remains valuable for
testing/debugging one specialist without paying for a full committee run
(FUNDAMENTAL_ANALYST_DESIGN.md §14, reaffirmed at INVESTMENT_COMMITTEE_
DESIGN.md §11). `AgentGenerationResponse`/`SpecialistFindingRead` are the
generic "{symbol, status, task_id}" / "pass result_json through as-is"
shapes every one of these five direct-invocation route pairs uses --
`FundamentalAnalysisGenerationResponse`/`FundamentalFindingRead` are kept
as aliases so v0.9's own route/response shape is untouched.

`CommitteeReportRead` (new, v1.0) is `GET /reports/{symbol}`'s response:
the Chair's `investment_committee` finding's `result_json` passed through
as-is (mirroring every other finding-read schema's own "pass the
already-structured payload through" choice), plus the `compliance_review`
finding's own verdict alongside it -- the two are always read together,
never independently, since a report is never served without knowing
whether Compliance approved it.
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


class AgentGenerationResponse(BaseModel):
    symbol: str
    status: str
    task_id: str


FundamentalAnalysisGenerationResponse = AgentGenerationResponse


class SpecialistFindingRead(BaseModel):
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


FundamentalFindingRead = SpecialistFindingRead


class CommitteeReportRead(BaseModel):
    company_id: uuid.UUID
    company_symbol: str
    result_json: dict
    compliance: dict
    confidence_score: float
    created_at: datetime
    updated_at: datetime

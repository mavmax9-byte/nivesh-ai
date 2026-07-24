"""AI Layer request/response schemas.

Shape follows the job-based API pattern from docs/v1 09-API-Design.md
section 9.4 -- report generation is asynchronous by design.
"""

import uuid

from pydantic import BaseModel


class AnalysisRequest(BaseModel):
    company_id: uuid.UUID
    force_refresh: bool = False


class AnalysisJobStatus(BaseModel):
    job_id: uuid.UUID
    status: str

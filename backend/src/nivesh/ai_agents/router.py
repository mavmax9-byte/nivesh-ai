"""AI Layer routes (placeholder).

Returns 501 Not Implemented via NotImplementedYetError until the Investment
Committee orchestrator (docs/v2 05-Investment-Committee.md) is built --
intentionally not stubbed with fake data, since fabricated AI output would
violate the explainability contract (docs/v2 07) before it even exists.
"""

from fastapi import APIRouter, Depends

from nivesh.ai_agents.orchestrator import InvestmentCommitteeOrchestrator
from nivesh.ai_agents.schemas import AnalysisJobStatus, AnalysisRequest

router = APIRouter(prefix="/reports", tags=["ai-agents"])


def get_orchestrator() -> InvestmentCommitteeOrchestrator:
    return InvestmentCommitteeOrchestrator()


@router.post("", response_model=AnalysisJobStatus, status_code=202)
async def request_analysis(
    payload: AnalysisRequest,
    orchestrator: InvestmentCommitteeOrchestrator = Depends(get_orchestrator),
) -> AnalysisJobStatus:
    job_id = await orchestrator.request_analysis(payload.company_id)
    return AnalysisJobStatus(job_id=job_id, status="queued")

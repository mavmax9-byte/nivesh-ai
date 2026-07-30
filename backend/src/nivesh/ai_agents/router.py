"""AI Layer routes.

Two route groups:

- `router` (`/reports`, placeholder, unchanged): the future Investment
  Committee orchestrator's job-based API. Returns 501 Not Implemented via
  NotImplementedYetError until that layer is built -- intentionally not
  stubbed with fake data, since fabricated AI output would violate the
  explainability contract (docs/v2 07) before it even exists.
- `fundamental_router` (`/agents/fundamental`, new in v0.9): direct
  invocation of the Fundamental Analyst, needed because the orchestrator
  that would otherwise be its only caller doesn't exist yet (see
  FUNDAMENTAL_ANALYST_DESIGN.md §14). Follows the standard "POST .../
  generate/... returns 202 + queued task" convention every other
  generate-style route in this codebase uses -- an LLM call is slow and
  costs real money, exactly the profile that convention exists for.
  `GET` reads the persisted `AgentFinding` the queued task most recently
  wrote (see ai_agents/models.py for why this module now has one), the
  same "service dependency built even for a read-only route" shape
  `technical_intelligence`/`knowledge_layer`'s routers already use.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.ai_agents.agents.fundamental.agent import FundamentalAnalystAgent
from nivesh.ai_agents.models import AGENT_CODE_FUNDAMENTAL_ANALYST
from nivesh.ai_agents.orchestrator import InvestmentCommitteeOrchestrator
from nivesh.ai_agents.providers.factory import get_llm_provider
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.ai_agents.schemas import (
    AnalysisJobStatus,
    AnalysisRequest,
    FundamentalAnalysisGenerationResponse,
    FundamentalFindingRead,
)
from nivesh.ai_agents.service import AIAgentsService
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import generate_fundamental_analysis
from nivesh.knowledge_layer.providers.factory import get_embedding_provider
from nivesh.research.repository import ResearchDossierRepository
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.retrieval_engine.service import RetrievalEngineService

router = APIRouter(prefix="/reports", tags=["ai-agents"])
fundamental_router = APIRouter(prefix="/agents/fundamental", tags=["ai-agents-fundamental"])


def get_orchestrator() -> InvestmentCommitteeOrchestrator:
    return InvestmentCommitteeOrchestrator()


@router.post("", response_model=AnalysisJobStatus, status_code=202)
async def request_analysis(
    payload: AnalysisRequest,
    orchestrator: InvestmentCommitteeOrchestrator = Depends(get_orchestrator),
) -> AnalysisJobStatus:
    job_id = await orchestrator.request_analysis(payload.company_id)
    return AnalysisJobStatus(job_id=job_id, status="queued")


def get_ai_agents_service(db: AsyncSession = Depends(get_db)) -> AIAgentsService:
    company_repository = CompanyRepository(db)
    agent = FundamentalAnalystAgent(
        retrieval_service=RetrievalEngineService(
            embedding_provider=get_embedding_provider(),
            company_repository=company_repository,
            evidence_repository=RetrievalRepository(db),
        ),
        llm_provider=get_llm_provider(),
        company_repository=company_repository,
    )
    return AIAgentsService(
        agent=agent,
        company_repository=company_repository,
        finding_repository=AgentFindingRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@fundamental_router.post(
    "/{symbol}", response_model=FundamentalAnalysisGenerationResponse, status_code=202
)
async def generate_fundamental_finding(symbol: str) -> FundamentalAnalysisGenerationResponse:
    task = generate_fundamental_analysis.delay(symbol.upper())
    return FundamentalAnalysisGenerationResponse(
        symbol=symbol.upper(), status="queued", task_id=task.id
    )


@fundamental_router.get("/{symbol}", response_model=FundamentalFindingRead)
async def get_fundamental_finding(
    symbol: str,
    service: AIAgentsService = Depends(get_ai_agents_service),
) -> FundamentalFindingRead:
    finding = await service.get_latest_finding(symbol)
    if finding is None:
        raise NotFoundError(
            f"No {AGENT_CODE_FUNDAMENTAL_ANALYST} finding exists for '{symbol}'. "
            f"POST /agents/fundamental/{symbol} to generate one."
        )
    return FundamentalFindingRead.model_validate(finding)

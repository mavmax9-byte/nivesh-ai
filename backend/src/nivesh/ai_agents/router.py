"""AI Layer routes.

Two kinds of route groups:

- `router` (`/reports`): the Investment Committee's job-based API. `POST`
  enqueues `run_investment_committee` (v1.0, real -- previously always
  `501`), resolving `company_id` to a symbol directly in the route handler
  and calling `.delay()`, the same "resolve, then `.delay()` the task"
  shape every specialist's own direct-invocation route already uses below
  (no orchestrator-layer indirection, see orchestrator.py's module
  docstring for why). `GET /reports/{symbol}` (new) returns the full
  committee bundle -- the Chair's synthesized decision plus the
  Compliance verdict, read together since a report is never served
  without knowing whether Compliance approved it (INVESTMENT_COMMITTEE_
  DESIGN.md §11).
- Five direct-invocation route groups (`/agents/fundamental`,
  `/agents/technical`, `/agents/valuation`, `/agents/news-sentiment`,
  `/agents/risk`) -- one per specialist, all identically shaped
  (`FUNDAMENTAL_ANALYST_DESIGN.md` §14, reaffirmed at INVESTMENT_
  COMMITTEE_DESIGN.md §11: even with the orchestrator now real,
  independent invocation remains valuable for testing/debugging one
  specialist without paying for a full committee run). Compliance gets no
  direct endpoint -- it has no per-company evidence-retrieval story of its
  own; its verdict is only ever visible via `GET /reports/{symbol}`.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.ai_agents.agents.fundamental.agent import FundamentalAnalystAgent
from nivesh.ai_agents.agents.news_sentiment.agent import NewsSentimentAnalystAgent
from nivesh.ai_agents.agents.risk.agent import RiskAnalystAgent
from nivesh.ai_agents.agents.technical.agent import TechnicalAnalystAgent
from nivesh.ai_agents.agents.valuation.agent import ValuationAnalystAgent
from nivesh.ai_agents.models import AGENT_CODE_COMPLIANCE_REVIEW, AGENT_CODE_INVESTMENT_COMMITTEE
from nivesh.ai_agents.providers.factory import get_llm_provider
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.ai_agents.schemas import (
    AgentGenerationResponse,
    AnalysisJobStatus,
    AnalysisRequest,
    CommitteeReportRead,
    SpecialistFindingRead,
)
from nivesh.ai_agents.service import AIAgentsService
from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.ingestion.tasks import (
    generate_fundamental_analysis,
    generate_news_sentiment_analysis,
    generate_risk_analysis,
    generate_technical_analysis,
    generate_valuation_analysis,
    run_investment_committee,
)
from nivesh.knowledge_layer.providers.factory import get_embedding_provider
from nivesh.research.repository import ResearchDossierRepository
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.retrieval_engine.service import RetrievalEngineService

router = APIRouter(prefix="/reports", tags=["ai-agents"])
fundamental_router = APIRouter(prefix="/agents/fundamental", tags=["ai-agents-fundamental"])
technical_router = APIRouter(prefix="/agents/technical", tags=["ai-agents-technical"])
valuation_router = APIRouter(prefix="/agents/valuation", tags=["ai-agents-valuation"])
news_sentiment_router = APIRouter(
    prefix="/agents/news-sentiment", tags=["ai-agents-news-sentiment"]
)
risk_router = APIRouter(prefix="/agents/risk", tags=["ai-agents-risk"])


@router.post("", response_model=AnalysisJobStatus, status_code=202)
async def request_analysis(
    payload: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalysisJobStatus:
    company = await CompanyRepository(db).get_by_id(payload.company_id)
    if company is None:
        raise NotFoundError(f"No company found with id '{payload.company_id}'")
    task = run_investment_committee.delay(company.symbol)
    return AnalysisJobStatus(job_id=uuid.UUID(task.id), status="queued")


@router.get("/{symbol}", response_model=CommitteeReportRead)
async def get_committee_report(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> CommitteeReportRead:
    company_repository = CompanyRepository(db)
    finding_repository = AgentFindingRepository(db)

    company = await company_repository.get_by_symbol(symbol)
    if company is None:
        raise NotFoundError(f"No company found with symbol '{symbol}'")

    decision_row = await finding_repository.get_latest(company.id, AGENT_CODE_INVESTMENT_COMMITTEE)
    compliance_row = await finding_repository.get_latest(company.id, AGENT_CODE_COMPLIANCE_REVIEW)
    if (
        decision_row is None
        or compliance_row is None
        or not compliance_row.result_json.get("approved", False)
    ):
        raise NotFoundError(
            f"No committee decision exists for '{symbol}', or the most recent run was rejected "
            f"by compliance review. POST /reports to generate one."
        )

    return CommitteeReportRead(
        company_id=company.id,
        company_symbol=company.symbol,
        result_json=decision_row.result_json,
        compliance=compliance_row.result_json,
        confidence_score=decision_row.confidence_score,
        created_at=decision_row.created_at,
        updated_at=decision_row.updated_at,
    )


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


@fundamental_router.post("/{symbol}", response_model=AgentGenerationResponse, status_code=202)
async def generate_fundamental_finding(symbol: str) -> AgentGenerationResponse:
    task = generate_fundamental_analysis.delay(symbol.upper())
    return AgentGenerationResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@fundamental_router.get("/{symbol}", response_model=SpecialistFindingRead)
async def get_fundamental_finding(
    symbol: str,
    service: AIAgentsService = Depends(get_ai_agents_service),
) -> SpecialistFindingRead:
    finding = await service.get_latest_finding(symbol)
    if finding is None:
        raise NotFoundError(
            f"No fundamental_analyst finding exists for '{symbol}'. "
            f"POST /agents/fundamental/{symbol} to generate one."
        )
    return SpecialistFindingRead.model_validate(finding)


def get_technical_service(db: AsyncSession = Depends(get_db)) -> AIAgentsService:
    company_repository = CompanyRepository(db)
    agent = TechnicalAnalystAgent(
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


@technical_router.post("/{symbol}", response_model=AgentGenerationResponse, status_code=202)
async def generate_technical_finding(symbol: str) -> AgentGenerationResponse:
    task = generate_technical_analysis.delay(symbol.upper())
    return AgentGenerationResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@technical_router.get("/{symbol}", response_model=SpecialistFindingRead)
async def get_technical_finding(
    symbol: str,
    service: AIAgentsService = Depends(get_technical_service),
) -> SpecialistFindingRead:
    finding = await service.get_latest_finding(symbol)
    if finding is None:
        raise NotFoundError(
            f"No technical_analyst finding exists for '{symbol}'. "
            f"POST /agents/technical/{symbol} to generate one."
        )
    return SpecialistFindingRead.model_validate(finding)


def get_valuation_service(db: AsyncSession = Depends(get_db)) -> AIAgentsService:
    company_repository = CompanyRepository(db)
    agent = ValuationAnalystAgent(
        retrieval_service=RetrievalEngineService(
            embedding_provider=get_embedding_provider(),
            company_repository=company_repository,
            evidence_repository=RetrievalRepository(db),
        ),
        llm_provider=get_llm_provider(),
        company_repository=company_repository,
        statement_repository=FinancialStatementRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )
    return AIAgentsService(
        agent=agent,
        company_repository=company_repository,
        finding_repository=AgentFindingRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@valuation_router.post("/{symbol}", response_model=AgentGenerationResponse, status_code=202)
async def generate_valuation_finding(symbol: str) -> AgentGenerationResponse:
    task = generate_valuation_analysis.delay(symbol.upper())
    return AgentGenerationResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@valuation_router.get("/{symbol}", response_model=SpecialistFindingRead)
async def get_valuation_finding(
    symbol: str,
    service: AIAgentsService = Depends(get_valuation_service),
) -> SpecialistFindingRead:
    finding = await service.get_latest_finding(symbol)
    if finding is None:
        raise NotFoundError(
            f"No valuation_analyst finding exists for '{symbol}'. "
            f"POST /agents/valuation/{symbol} to generate one."
        )
    return SpecialistFindingRead.model_validate(finding)


def get_news_sentiment_service(db: AsyncSession = Depends(get_db)) -> AIAgentsService:
    company_repository = CompanyRepository(db)
    agent = NewsSentimentAnalystAgent(
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


@news_sentiment_router.post("/{symbol}", response_model=AgentGenerationResponse, status_code=202)
async def generate_news_sentiment_finding(symbol: str) -> AgentGenerationResponse:
    task = generate_news_sentiment_analysis.delay(symbol.upper())
    return AgentGenerationResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@news_sentiment_router.get("/{symbol}", response_model=SpecialistFindingRead)
async def get_news_sentiment_finding(
    symbol: str,
    service: AIAgentsService = Depends(get_news_sentiment_service),
) -> SpecialistFindingRead:
    finding = await service.get_latest_finding(symbol)
    if finding is None:
        raise NotFoundError(
            f"No news_sentiment_analyst finding exists for '{symbol}'. "
            f"POST /agents/news-sentiment/{symbol} to generate one."
        )
    return SpecialistFindingRead.model_validate(finding)


def get_risk_service(db: AsyncSession = Depends(get_db)) -> AIAgentsService:
    company_repository = CompanyRepository(db)
    agent = RiskAnalystAgent(
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


@risk_router.post("/{symbol}", response_model=AgentGenerationResponse, status_code=202)
async def generate_risk_finding(symbol: str) -> AgentGenerationResponse:
    task = generate_risk_analysis.delay(symbol.upper())
    return AgentGenerationResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@risk_router.get("/{symbol}", response_model=SpecialistFindingRead)
async def get_risk_finding(
    symbol: str,
    service: AIAgentsService = Depends(get_risk_service),
) -> SpecialistFindingRead:
    finding = await service.get_latest_finding(symbol)
    if finding is None:
        raise NotFoundError(
            f"No risk_analyst finding exists for '{symbol}'. "
            f"POST /agents/risk/{symbol} to generate one."
        )
    return SpecialistFindingRead.model_validate(finding)

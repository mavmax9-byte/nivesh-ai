"""News Intelligence Engine routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import sync_company_news
from nivesh.news_intelligence.providers.factory import get_news_provider
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.news_intelligence.schemas import NewsArticleRead, NewsSyncResponse
from nivesh.news_intelligence.service import NewsIntelligenceService
from nivesh.research.repository import ResearchDossierRepository

router = APIRouter(prefix="/news", tags=["news-intelligence"])


def get_news_intelligence_service(db: AsyncSession = Depends(get_db)) -> NewsIntelligenceService:
    return NewsIntelligenceService(
        provider=get_news_provider(),
        company_repository=CompanyRepository(db),
        article_repository=NewsArticleRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@router.post("/sync/{symbol}", response_model=NewsSyncResponse, status_code=202)
async def sync_news(symbol: str) -> NewsSyncResponse:
    task = sync_company_news.delay(symbol.upper())
    return NewsSyncResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@router.get("/{symbol}", response_model=list[NewsArticleRead])
async def get_news(
    symbol: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: NewsIntelligenceService = Depends(get_news_intelligence_service),
) -> list[NewsArticleRead]:
    articles = await service.get_news(symbol, limit=limit, offset=offset)
    return [NewsArticleRead.model_validate(a) for a in articles]


@router.get("/{symbol}/category/{category}", response_model=list[NewsArticleRead])
async def get_news_by_category(
    symbol: str,
    category: str,
    limit: int = Query(default=50, le=200),
    service: NewsIntelligenceService = Depends(get_news_intelligence_service),
) -> list[NewsArticleRead]:
    articles = await service.get_news_by_category(symbol, category, limit=limit)
    return [NewsArticleRead.model_validate(a) for a in articles]

"""Knowledge Layer routes.

`GET /knowledge/{symbol}/search` is the one read endpoint in this codebase
that makes a live external API call (one embedding request for the query
text) inside a synchronous request/response cycle rather than queuing
Celery work -- this is correct, not an inconsistency: a search query is a
read that needs a fresh query embedding to compare against, not an
ingestion action with a "do the work later" option. `POST .../generate/`
still follows the standard "202 + queued task" convention every other
sync/generate route in this codebase uses, since generating embeddings for
a whole company's knowledge is real ingestion work.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.corporate_filings.repository import CorporateFilingRepository
from nivesh.dependencies import get_db
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.ingestion.tasks import generate_knowledge_embeddings
from nivesh.knowledge_layer.providers.factory import get_embedding_provider
from nivesh.knowledge_layer.repository import KnowledgeEmbeddingRepository
from nivesh.knowledge_layer.schemas import (
    KnowledgeEmbeddingRead,
    KnowledgeGenerationResponse,
    KnowledgeSearchResponse,
    KnowledgeSearchResultRead,
)
from nivesh.knowledge_layer.service import KnowledgeLayerService
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.research.repository import ResearchDossierRepository

router = APIRouter(prefix="/knowledge", tags=["knowledge-layer"])


def get_knowledge_layer_service(db: AsyncSession = Depends(get_db)) -> KnowledgeLayerService:
    return KnowledgeLayerService(
        provider=get_embedding_provider(),
        company_repository=CompanyRepository(db),
        filing_repository=CorporateFilingRepository(db),
        extraction_repository=DocumentExtractionRepository(db),
        article_repository=NewsArticleRepository(db),
        dossier_repository=ResearchDossierRepository(db),
        embedding_repository=KnowledgeEmbeddingRepository(db),
    )


@router.post("/generate/{symbol}", response_model=KnowledgeGenerationResponse, status_code=202)
async def generate_embeddings(symbol: str) -> KnowledgeGenerationResponse:
    task = generate_knowledge_embeddings.delay(symbol.upper())
    return KnowledgeGenerationResponse(symbol=symbol.upper(), status="queued", task_id=task.id)


@router.get("/{symbol}", response_model=list[KnowledgeEmbeddingRead])
async def list_embeddings(
    symbol: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: KnowledgeLayerService = Depends(get_knowledge_layer_service),
) -> list[KnowledgeEmbeddingRead]:
    embeddings = await service.list_embeddings(symbol, limit=limit, offset=offset)
    return [KnowledgeEmbeddingRead.model_validate(e) for e in embeddings]


@router.get("/{symbol}/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    symbol: str,
    query: str = Query(..., min_length=1),
    limit: int = Query(default=10, le=50),
    service: KnowledgeLayerService = Depends(get_knowledge_layer_service),
) -> KnowledgeSearchResponse:
    hits = await service.search(symbol, query, limit=limit)
    return KnowledgeSearchResponse(
        symbol=symbol.upper(),
        query=query,
        results=[
            KnowledgeSearchResultRead(
                source_type=hit.source_type,
                source_table=hit.source_table,
                source_id=hit.source_id,
                title=hit.title,
                content_text=hit.content_text,
                similarity=hit.similarity,
            )
            for hit in hits
        ],
    )

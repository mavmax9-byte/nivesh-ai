"""Retrieval Engine routes.

Every route here is a `GET` -- this module never triggers ingestion or
background work of its own (it only reads what other modules already
persisted), and per the explicit v0.8 planning decision, no retrieval
call is persisted either, so there is nothing to `POST`/queue and nothing
to fetch back by id later. `query` is required on every route: structured
evidence is always attached regardless of query content, but semantic
matching -- half of what makes this "hybrid" retrieval -- has no meaning
without one.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.dependencies import get_db
from nivesh.knowledge_layer.providers.factory import get_embedding_provider
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.retrieval_engine.schemas import (
    ContextPackageRead,
    EvidenceItemRead,
    RetrievalDiagnosticsRead,
    RetrievalResponse,
)
from nivesh.retrieval_engine.service import DEFAULT_LIMIT, RetrievalEngineService

router = APIRouter(prefix="/retrieval", tags=["retrieval-engine"])


def get_retrieval_engine_service(
    db: AsyncSession = Depends(get_db),
) -> RetrievalEngineService:
    return RetrievalEngineService(
        embedding_provider=get_embedding_provider(),
        company_repository=CompanyRepository(db),
        evidence_repository=RetrievalRepository(db),
    )


@router.get("/{symbol}/evidence", response_model=RetrievalResponse)
async def retrieve_evidence(
    symbol: str,
    query: str = Query(..., min_length=1),
    limit: int = Query(default=DEFAULT_LIMIT, le=100),
    service: RetrievalEngineService = Depends(get_retrieval_engine_service),
) -> RetrievalResponse:
    evidence = await service.retrieve_evidence(symbol, query, limit=limit)
    return RetrievalResponse(
        symbol=symbol.upper(),
        query=query,
        evidence=[EvidenceItemRead.model_validate(item) for item in evidence],
    )


@router.get("/{symbol}/context", response_model=ContextPackageRead)
async def retrieve_context_package(
    symbol: str,
    query: str = Query(..., min_length=1),
    limit: int = Query(default=DEFAULT_LIMIT, le=100),
    service: RetrievalEngineService = Depends(get_retrieval_engine_service),
) -> ContextPackageRead:
    package = await service.build_context_package(symbol, query, limit=limit)
    return ContextPackageRead(
        symbol=package.symbol,
        query=package.query,
        generated_at=package.generated_at,
        evidence=[EvidenceItemRead.model_validate(item) for item in package.evidence],
        context_text=package.context_text,
    )


@router.get("/{symbol}/inspect", response_model=RetrievalDiagnosticsRead)
async def inspect_retrieval(
    symbol: str,
    query: str = Query(..., min_length=1),
    limit: int = Query(default=DEFAULT_LIMIT, le=100),
    service: RetrievalEngineService = Depends(get_retrieval_engine_service),
) -> RetrievalDiagnosticsRead:
    diagnostics = await service.inspect_retrieval(symbol, query, limit=limit)
    return RetrievalDiagnosticsRead(
        symbol=diagnostics.symbol,
        query=diagnostics.query,
        fetched_counts=diagnostics.fetched_counts,
        total_fetched=diagnostics.total_fetched,
        total_after_dedup=diagnostics.total_after_dedup,
        total_returned=diagnostics.total_returned,
        evidence=[EvidenceItemRead.model_validate(item) for item in diagnostics.evidence],
    )

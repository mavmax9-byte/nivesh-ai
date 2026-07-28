"""Document Intelligence Engine routes."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.companies.repository import CompanyRepository
from nivesh.corporate_filings.repository import CorporateFilingRepository
from nivesh.dependencies import get_db
from nivesh.document_intelligence.providers.factory import get_document_extraction_provider
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.document_intelligence.schemas import (
    DocumentExtractionDetailRead,
    DocumentExtractionRead,
    DocumentExtractionSyncResponse,
)
from nivesh.document_intelligence.service import DocumentIntelligenceService
from nivesh.ingestion.tasks import extract_filing_document
from nivesh.research.repository import ResearchDossierRepository

router = APIRouter(prefix="/document-intelligence", tags=["document-intelligence"])


def get_document_intelligence_service(
    db: AsyncSession = Depends(get_db),
) -> DocumentIntelligenceService:
    return DocumentIntelligenceService(
        provider=get_document_extraction_provider(),
        filing_repository=CorporateFilingRepository(db),
        company_repository=CompanyRepository(db),
        extraction_repository=DocumentExtractionRepository(db),
        dossier_repository=ResearchDossierRepository(db),
    )


@router.post(
    "/extract/{filing_version_id}",
    response_model=DocumentExtractionSyncResponse,
    status_code=202,
)
async def extract_document(filing_version_id: uuid.UUID) -> DocumentExtractionSyncResponse:
    task = extract_filing_document.delay(str(filing_version_id))
    return DocumentExtractionSyncResponse(
        filing_version_id=filing_version_id, status="queued", task_id=task.id
    )


@router.get("/filing-versions/{filing_version_id}", response_model=DocumentExtractionDetailRead)
async def get_document_extraction(
    filing_version_id: uuid.UUID,
    service: DocumentIntelligenceService = Depends(get_document_intelligence_service),
) -> DocumentExtractionDetailRead:
    extraction = await service.get_extraction(filing_version_id)
    return DocumentExtractionDetailRead.model_validate(extraction)


@router.get("/{symbol}", response_model=list[DocumentExtractionRead])
async def get_document_extractions_for_symbol(
    symbol: str,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    service: DocumentIntelligenceService = Depends(get_document_intelligence_service),
) -> list[DocumentExtractionRead]:
    extractions = await service.get_extractions_for_symbol(symbol, limit=limit, offset=offset)
    return [DocumentExtractionRead.model_validate(e) for e in extractions]

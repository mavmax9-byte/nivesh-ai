"""Celery tasks for market data ingestion and research pipeline refresh.

Tasks run in worker processes outside any request/response cycle, so each
invocation creates and closes its own database session and event loop
rather than reusing FastAPI's request-scoped dependencies. `engine` is a
single module-level object shared by every task the worker process ever
runs, but each task's `asyncio.run()` gives it a brand new event loop --
and SQLAlchemy's async connection pool must never hand out a connection
across two different event loops (the pool has no way to know a
previous loop closed; on Windows the pooled connection's ping fails deep
inside its severed proactor socket instead of raising a catchable
DBAPI-level "disconnected" error). Each task therefore disposes the pool
before its event loop closes, so the next task's loop always starts from
an empty pool and opens fresh connections bound to itself.
"""

import asyncio
import logging
import uuid

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.core.celery_app import celery_app
from nivesh.core.db import AsyncSessionLocal, engine
from nivesh.corporate_filings.providers.factory import get_corporate_filings_provider
from nivesh.corporate_filings.repository import (
    CorporateFilingRepository,
    FilingCategoryRepository,
    FilingSourceRepository,
)
from nivesh.corporate_filings.service import CorporateFilingsService
from nivesh.document_intelligence.providers.factory import get_document_extraction_provider
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.document_intelligence.service import DocumentIntelligenceService
from nivesh.document_intelligence.validation import (
    EXTRACTABLE_FILING_TYPES,
    DuplicateExtractionError,
)
from nivesh.financials.providers.factory import get_financial_data_provider
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.financials.service import FinancialStatementService
from nivesh.market_data.providers.factory import get_market_data_provider
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.market_data.service import MarketDataService
from nivesh.research.repository import ResearchDossierRepository
from nivesh.research.service import ResearchPipelineService

logger = logging.getLogger(__name__)


async def _refresh_company_dossier(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = ResearchPipelineService(
                company_repository=CompanyRepository(session),
                dossier_repository=ResearchDossierRepository(session),
                ohlcv_repository=HistoricalOHLCVRepository(session),
                corporate_action_repository=CorporateActionRepository(session),
            )
            result = await service.refresh_dossier(symbol)
            return {
                "symbol": result.symbol,
                "changed": result.changed,
                "version_number": result.version_number,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.refresh_company_dossier",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def refresh_company_dossier(self, symbol: str) -> dict:
    """Rebuilds the latest research dossier version for a company.

    Deterministic and idempotent: if nothing has changed since the last
    version (per ResearchPipelineService's watermark comparison), no new
    version is created and this is a cheap no-op.
    """
    try:
        return asyncio.run(_refresh_company_dossier(symbol))
    except Exception as exc:
        logger.exception("refresh_company_dossier_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _sync_company_market_data(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = MarketDataService(
                provider=get_market_data_provider(),
                company_repository=CompanyRepository(session),
                exchange_repository=ExchangeRepository(session),
                ohlcv_repository=HistoricalOHLCVRepository(session),
                corporate_action_repository=CorporateActionRepository(session),
            )
            result = await service.sync_company(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "bars_synced": result.bars_synced,
                "bars_skipped": result.bars_skipped,
                "actions_synced": result.actions_synced,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.sync_company_market_data",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_company_market_data(self, symbol: str) -> dict:
    try:
        result = asyncio.run(_sync_company_market_data(symbol))
    except Exception as exc:
        logger.exception("sync_company_market_data_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc

    # Every successful sync triggers a dossier refresh; refresh_dossier's own
    # watermark check (not this call site) is what decides whether that
    # actually produces a new version.
    refresh_company_dossier.delay(result["symbol"])
    return result


async def _sync_company_financials(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = FinancialStatementService(
                provider=get_financial_data_provider(),
                company_repository=CompanyRepository(session),
                statement_repository=FinancialStatementRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.sync_company_financials(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "statements_synced": result.statements_synced,
                "statements_unchanged": result.statements_unchanged,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.sync_company_financials",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_company_financials(self, symbol: str) -> dict:
    """Rebuilds financial statement history for a company.

    Deterministic and idempotent, mirroring sync_company_market_data:
    unchanged periods are skipped rather than re-versioned (see
    FinancialStatementService._is_unchanged), so re-running this on
    already-current data is a cheap no-op.
    """
    try:
        return asyncio.run(_sync_company_financials(symbol))
    except Exception as exc:
        logger.exception("sync_company_financials_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _sync_company_filings(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = CorporateFilingsService(
                provider=get_corporate_filings_provider(),
                company_repository=CompanyRepository(session),
                category_repository=FilingCategoryRepository(session),
                source_repository=FilingSourceRepository(session),
                filing_repository=CorporateFilingRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.sync_company_filings(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "filings_synced": result.filings_synced,
                "filings_unchanged": result.filings_unchanged,
                "synced_filing_versions": [
                    {"filing_version_id": str(v.filing_version_id), "filing_type": v.filing_type}
                    for v in result.synced_filing_versions
                ],
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.sync_company_filings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_company_filings(self, symbol: str) -> dict:
    """Rebuilds corporate filings metadata for a company.

    Deterministic and idempotent, mirroring sync_company_financials:
    unchanged filings are skipped rather than re-versioned (see
    CorporateFilingsService's checksum-equality check), so re-running this
    on already-current data is a cheap no-op.
    """
    try:
        result = asyncio.run(_sync_company_filings(symbol))
    except Exception as exc:
        logger.exception("sync_company_filings_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc

    # Document Intelligence is triggered only for filing versions this very
    # sync just created (never for filings that already existed or were
    # unchanged) and only for filing types it knows how to extract -- see
    # CorporateFilingsService.sync_company_filings' synced_filing_versions.
    for version in result["synced_filing_versions"]:
        if version["filing_type"] in EXTRACTABLE_FILING_TYPES:
            extract_filing_document.delay(version["filing_version_id"])

    return result


async def _extract_filing_document(filing_version_id: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = DocumentIntelligenceService(
                provider=get_document_extraction_provider(),
                filing_repository=CorporateFilingRepository(session),
                company_repository=CompanyRepository(session),
                extraction_repository=DocumentExtractionRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            extraction = await service.extract_filing_document(uuid.UUID(filing_version_id))
            return {
                "filing_version_id": str(extraction.filing_version_id),
                "extraction_status": extraction.extraction_status,
                "page_count": extraction.page_count,
                "section_count": extraction.section_count,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.extract_filing_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def extract_filing_document(self, filing_version_id: str) -> dict:
    """Extracts structured text for one filing version (Document Intelligence).

    A filing version that already has an extraction raises
    DuplicateExtractionError (see DocumentIntelligenceService); that is a
    conflict, not a transient failure, so it is not retried. Provider/network
    failures and any other error are retried, mirroring every other task in
    this module.
    """
    try:
        return asyncio.run(_extract_filing_document(filing_version_id))
    except DuplicateExtractionError:
        logger.info(
            "extract_filing_document_already_extracted",
            extra={"filing_version_id": filing_version_id},
        )
        raise
    except Exception as exc:
        logger.exception(
            "extract_filing_document_failed", extra={"filing_version_id": filing_version_id}
        )
        raise self.retry(exc=exc) from exc

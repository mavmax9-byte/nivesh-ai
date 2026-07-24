"""Celery tasks for market data ingestion and research pipeline refresh.

Tasks run in worker processes outside any request/response cycle, so each
invocation creates and closes its own database session and event loop
rather than reusing FastAPI's request-scoped dependencies.
"""

import asyncio
import logging

from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.core.celery_app import celery_app
from nivesh.core.db import AsyncSessionLocal
from nivesh.market_data.providers.factory import get_market_data_provider
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.market_data.service import MarketDataService
from nivesh.research.repository import ResearchDossierRepository
from nivesh.research.service import ResearchPipelineService

logger = logging.getLogger(__name__)


async def _refresh_company_dossier(symbol: str) -> dict:
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

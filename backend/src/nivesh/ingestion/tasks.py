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

from nivesh.ai_agents.agents.fundamental.agent import FundamentalAnalystAgent
from nivesh.ai_agents.agents.news_sentiment.agent import NewsSentimentAnalystAgent
from nivesh.ai_agents.agents.risk.agent import RiskAnalystAgent
from nivesh.ai_agents.agents.technical.agent import TechnicalAnalystAgent
from nivesh.ai_agents.agents.valuation.agent import ValuationAnalystAgent
from nivesh.ai_agents.committee.exceptions import (
    CommitteeQuorumNotMetError,
    ComplianceRejectedError,
)
from nivesh.ai_agents.guardrails import InvestmentAdviceDetectedError
from nivesh.ai_agents.orchestrator import InvestmentCommitteeOrchestrator
from nivesh.ai_agents.providers.factory import get_llm_provider
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.ai_agents.service import AIAgentsService
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
from nivesh.knowledge_layer.providers.factory import get_embedding_provider
from nivesh.knowledge_layer.repository import KnowledgeEmbeddingRepository
from nivesh.knowledge_layer.service import KnowledgeLayerService
from nivesh.market_data.providers.factory import get_market_data_provider
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.market_data.service import MarketDataService
from nivesh.news_intelligence.providers.factory import get_news_provider
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.news_intelligence.service import NewsIntelligenceService
from nivesh.research.repository import ResearchDossierRepository
from nivesh.research.service import ResearchPipelineService
from nivesh.retrieval_engine.repository import RetrievalRepository
from nivesh.retrieval_engine.service import RetrievalEngineService
from nivesh.technical_intelligence.providers.factory import get_technical_data_provider
from nivesh.technical_intelligence.repository import TechnicalIndicatorRepository
from nivesh.technical_intelligence.service import TechnicalIntelligenceService

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
    # actually produces a new version. It also triggers technical indicator
    # generation, since indicators are computed from the OHLCV bars this
    # sync just wrote -- see technical_intelligence/service.py.
    refresh_company_dossier.delay(result["symbol"])
    generate_technical_indicators.delay(result["symbol"])
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


async def _sync_company_news(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = NewsIntelligenceService(
                provider=get_news_provider(),
                company_repository=CompanyRepository(session),
                article_repository=NewsArticleRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.sync_company_news(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "articles_synced": result.articles_synced,
                "articles_unchanged": result.articles_unchanged,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.sync_company_news",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def sync_company_news(self, symbol: str) -> dict:
    """Rebuilds recent news article history for a company.

    Deterministic and idempotent, mirroring sync_company_financials:
    articles already stored (per checksum) are skipped rather than
    duplicated (see NewsIntelligenceService._persist_article), so
    re-running this on already-current data is a cheap no-op. Does not
    auto-chain into any further task -- there is no downstream module that
    consumes news articles yet, the same position sync_company_financials
    is in today.
    """
    try:
        return asyncio.run(_sync_company_news(symbol))
    except Exception as exc:
        logger.exception("sync_company_news_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_technical_indicators(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            ohlcv_repository = HistoricalOHLCVRepository(session)
            service = TechnicalIntelligenceService(
                provider=get_technical_data_provider(ohlcv_repository),
                company_repository=CompanyRepository(session),
                indicator_repository=TechnicalIndicatorRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.generate_indicators(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "indicators_generated": result.indicators_generated,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_technical_indicators",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_technical_indicators(self, symbol: str) -> dict:
    """Recomputes technical indicators for a company over a bounded
    trailing window of recent OHLCV history (see
    technical_intelligence/service.py for why bounded, not full history).

    Deterministic and idempotent: every value is a pure recomputation
    upserted by (company_id, trading_date, indicator_name), so re-running
    this is always safe and simply overwrites with the same result if
    nothing has changed. A company with fewer than the minimum required
    price bars raises InsufficientHistoryError, which -- like every other
    validation failure in this codebase -- is retried rather than treated
    as a permanent conflict; see PROJECT_CONTEXT.md's Celery section for
    why that imperfect-but-consistent behavior is kept.
    """
    try:
        return asyncio.run(_generate_technical_indicators(symbol))
    except Exception as exc:
        logger.exception("generate_technical_indicators_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_knowledge_embeddings(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = KnowledgeLayerService(
                provider=get_embedding_provider(),
                company_repository=CompanyRepository(session),
                filing_repository=CorporateFilingRepository(session),
                extraction_repository=DocumentExtractionRepository(session),
                article_repository=NewsArticleRepository(session),
                dossier_repository=ResearchDossierRepository(session),
                embedding_repository=KnowledgeEmbeddingRepository(session),
            )
            result = await service.generate_embeddings(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "embeddings_generated": result.embeddings_generated,
                "embeddings_unchanged": result.embeddings_unchanged,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_knowledge_embeddings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_knowledge_embeddings(self, symbol: str) -> dict:
    """Gathers a company's textual knowledge (profile, filings, document
    sections, news, research summaries) and embeds whatever has changed
    since the last run (see knowledge_layer/service.py for the
    checksum-skip mechanism that keeps repeat runs cheap).

    Deliberately **not** auto-chained from any upstream sync task in this
    version -- knowledge sources span four different upstream modules
    (news, filings, document extraction, research dossier refresh), and
    each embedding call has a real cost; wiring this to fire automatically
    after every one of those syncs is a reasonable future step, not
    assumed here. Triggered only via POST /knowledge/generate/{symbol}
    today. Retried like every other task on failure -- a missing
    OPENAI_API_KEY (EmbeddingProviderError) is retried the same as any
    other error, consistent with this codebase's established "retry
    everything, even permanent failures" behavior (see PROJECT_CONTEXT.md's
    Celery section for why that's kept rather than special-cased here).
    """
    try:
        return asyncio.run(_generate_knowledge_embeddings(symbol))
    except Exception as exc:
        logger.exception("generate_knowledge_embeddings_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_fundamental_analysis(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            company_repository = CompanyRepository(session)
            agent = FundamentalAnalystAgent(
                retrieval_service=RetrievalEngineService(
                    embedding_provider=get_embedding_provider(),
                    company_repository=company_repository,
                    evidence_repository=RetrievalRepository(session),
                ),
                llm_provider=get_llm_provider(),
                company_repository=company_repository,
            )
            service = AIAgentsService(
                agent=agent,
                company_repository=company_repository,
                finding_repository=AgentFindingRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.run_analysis(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "agent_code": result.agent_code,
                "confidence_score": result.confidence_score,
                "evidence_sufficiency": result.evidence_sufficiency,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_fundamental_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_fundamental_analysis(self, symbol: str) -> dict:
    """Runs the Fundamental Analyst (ai_agents' first concrete specialist
    agent, v0.9) for a company: retrieves ranked evidence via
    RetrievalEngineService (reusing it exactly as-is -- zero new
    retrieval logic, see agents/fundamental/agent.py), calls the LLM
    behind the LLMProvider abstraction, validates/guards the structured
    output (citation enforcement, investment-advice-language rejection --
    see agents/fundamental/validation.py), persists the result to
    agent_findings, and links it into the Research Dossier.

    Unlike retrieval_engine's semantic leg, a failed/unparseable LLM call
    is never silently degraded into a placeholder finding -- see
    agent.py's module docstring. LLMProviderError/LLMResponseParsingError
    are retried like any other failure in this codebase (see
    PROJECT_CONTEXT.md's Celery section for why "retry everything, even
    permanent failures" is kept rather than special-cased here).
    InvestmentAdviceDetectedError is the one exception to that -- like
    DuplicateExtractionError, it represents a genuine, non-transient
    rejection (retrying the identical prompt against the identical
    evidence would not produce a materially different outcome) and is
    logged and left failed, not retried.

    Not auto-chained from any upstream sync, for the same cost-profile
    reason generate_knowledge_embeddings isn't -- triggered only via
    POST /agents/fundamental/{symbol} today.
    """
    try:
        return asyncio.run(_generate_fundamental_analysis(symbol))
    except InvestmentAdviceDetectedError:
        logger.error("generate_fundamental_analysis_advice_rejected", extra={"symbol": symbol})
        raise
    except Exception as exc:
        logger.exception("generate_fundamental_analysis_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_technical_analysis(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            company_repository = CompanyRepository(session)
            agent = TechnicalAnalystAgent(
                retrieval_service=RetrievalEngineService(
                    embedding_provider=get_embedding_provider(),
                    company_repository=company_repository,
                    evidence_repository=RetrievalRepository(session),
                ),
                llm_provider=get_llm_provider(),
                company_repository=company_repository,
            )
            service = AIAgentsService(
                agent=agent,
                company_repository=company_repository,
                finding_repository=AgentFindingRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.run_analysis(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "agent_code": result.agent_code,
                "confidence_score": result.confidence_score,
                "evidence_sufficiency": result.evidence_sufficiency,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_technical_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_technical_analysis(self, symbol: str) -> dict:
    """Runs the Technical Analyst (v1.0) standalone -- see
    generate_fundamental_analysis's docstring for the shared retry/
    rejection semantics every ai_agents generation task follows."""
    try:
        return asyncio.run(_generate_technical_analysis(symbol))
    except InvestmentAdviceDetectedError:
        logger.error("generate_technical_analysis_advice_rejected", extra={"symbol": symbol})
        raise
    except Exception as exc:
        logger.exception("generate_technical_analysis_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_valuation_analysis(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            company_repository = CompanyRepository(session)
            agent = ValuationAnalystAgent(
                retrieval_service=RetrievalEngineService(
                    embedding_provider=get_embedding_provider(),
                    company_repository=company_repository,
                    evidence_repository=RetrievalRepository(session),
                ),
                llm_provider=get_llm_provider(),
                company_repository=company_repository,
                statement_repository=FinancialStatementRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            service = AIAgentsService(
                agent=agent,
                company_repository=company_repository,
                finding_repository=AgentFindingRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.run_analysis(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "agent_code": result.agent_code,
                "confidence_score": result.confidence_score,
                "evidence_sufficiency": result.evidence_sufficiency,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_valuation_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_valuation_analysis(self, symbol: str) -> dict:
    """Runs the Valuation Analyst (v1.0) standalone, including its own
    computed-P/E step (agents/valuation/ratios.py) -- see
    generate_fundamental_analysis's docstring for the shared retry/
    rejection semantics every ai_agents generation task follows."""
    try:
        return asyncio.run(_generate_valuation_analysis(symbol))
    except InvestmentAdviceDetectedError:
        logger.error("generate_valuation_analysis_advice_rejected", extra={"symbol": symbol})
        raise
    except Exception as exc:
        logger.exception("generate_valuation_analysis_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_news_sentiment_analysis(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            company_repository = CompanyRepository(session)
            agent = NewsSentimentAnalystAgent(
                retrieval_service=RetrievalEngineService(
                    embedding_provider=get_embedding_provider(),
                    company_repository=company_repository,
                    evidence_repository=RetrievalRepository(session),
                ),
                llm_provider=get_llm_provider(),
                company_repository=company_repository,
            )
            service = AIAgentsService(
                agent=agent,
                company_repository=company_repository,
                finding_repository=AgentFindingRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.run_analysis(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "agent_code": result.agent_code,
                "confidence_score": result.confidence_score,
                "evidence_sufficiency": result.evidence_sufficiency,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_news_sentiment_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_news_sentiment_analysis(self, symbol: str) -> dict:
    """Runs the News & Sentiment Analyst (v1.0) standalone -- see
    generate_fundamental_analysis's docstring for the shared retry/
    rejection semantics every ai_agents generation task follows."""
    try:
        return asyncio.run(_generate_news_sentiment_analysis(symbol))
    except InvestmentAdviceDetectedError:
        logger.error("generate_news_sentiment_analysis_advice_rejected", extra={"symbol": symbol})
        raise
    except Exception as exc:
        logger.exception("generate_news_sentiment_analysis_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _generate_risk_analysis(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            company_repository = CompanyRepository(session)
            agent = RiskAnalystAgent(
                retrieval_service=RetrievalEngineService(
                    embedding_provider=get_embedding_provider(),
                    company_repository=company_repository,
                    evidence_repository=RetrievalRepository(session),
                ),
                llm_provider=get_llm_provider(),
                company_repository=company_repository,
            )
            service = AIAgentsService(
                agent=agent,
                company_repository=company_repository,
                finding_repository=AgentFindingRepository(session),
                dossier_repository=ResearchDossierRepository(session),
            )
            result = await service.run_analysis(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "agent_code": result.agent_code,
                "confidence_score": result.confidence_score,
                "evidence_sufficiency": result.evidence_sufficiency,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.generate_risk_analysis",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_risk_analysis(self, symbol: str) -> dict:
    """Runs the Risk Analyst (v1.0) standalone -- see
    generate_fundamental_analysis's docstring for the shared retry/
    rejection semantics every ai_agents generation task follows."""
    try:
        return asyncio.run(_generate_risk_analysis(symbol))
    except InvestmentAdviceDetectedError:
        logger.error("generate_risk_analysis_advice_rejected", extra={"symbol": symbol})
        raise
    except Exception as exc:
        logger.exception("generate_risk_analysis_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc


async def _run_investment_committee(symbol: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            company_repository = CompanyRepository(session)
            orchestrator = InvestmentCommitteeOrchestrator(
                retrieval_service=RetrievalEngineService(
                    embedding_provider=get_embedding_provider(),
                    company_repository=company_repository,
                    evidence_repository=RetrievalRepository(session),
                ),
                llm_provider=get_llm_provider(),
                company_repository=company_repository,
                statement_repository=FinancialStatementRepository(session),
                dossier_repository=ResearchDossierRepository(session),
                finding_repository=AgentFindingRepository(session),
            )
            result = await orchestrator.run(symbol)
            return {
                "company_id": str(result.company_id),
                "symbol": result.symbol,
                "succeeded_specialists": result.succeeded_specialists,
                "failed_specialists": result.failed_specialists,
                "compliance_approved": result.compliance_approved,
                "confidence_score": result.confidence_score,
            }
    finally:
        await engine.dispose()


@celery_app.task(
    name="ingestion.run_investment_committee",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_investment_committee(self, symbol: str) -> dict:
    """Runs the Investment Committee (v1.0's multi-agent orchestration
    layer) for a company: one shared Retrieval Engine call (§3), every
    specialist agent run over that shared evidence pool (Fundamental
    reused unchanged, plus Technical/Valuation/News & Sentiment/Risk, new
    in v1.0), the Committee Chair's synthesis, and the Compliance gate --
    see orchestrator.py for the full pipeline and INVESTMENT_COMMITTEE_
    DESIGN.md for the design this implements exactly.

    `CommitteeQuorumNotMetError` (Fundamental Analyst did not succeed) and
    `ComplianceRejectedError` (the Chair's draft was rejected -- but the
    rejection itself is already durably persisted as a `compliance_review`
    row by the time this is raised, see orchestrator.py) are both genuine,
    non-transient rejections, the same category `InvestmentAdviceDetectedError`
    and `DuplicateExtractionError` already are in this codebase -- logged
    and left failed, not retried, since retrying identical inputs would
    not produce a materially different outcome. Every other error is
    retried like any other task in this module.

    Not auto-chained from any upstream sync, for the same cost-profile
    reason `generate_fundamental_analysis` isn't -- triggered only via
    `POST /reports` today.
    """
    try:
        return asyncio.run(_run_investment_committee(symbol))
    except (CommitteeQuorumNotMetError, ComplianceRejectedError) as exc:
        logger.error(
            "run_investment_committee_rejected",
            extra={"symbol": symbol, "error_code": exc.error_code},
        )
        raise
    except Exception as exc:
        logger.exception("run_investment_committee_failed", extra={"symbol": symbol})
        raise self.retry(exc=exc) from exc

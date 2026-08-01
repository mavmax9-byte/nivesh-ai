"""Market Universe service.

Expands the platform from a single-company planner into a multi-company
one (v1.4) by managing an initial tracked universe (Nifty 50) and
deterministically screening it *before* any Investment Committee (LLM)
analysis is spent on it. This module makes **no LLM calls of its own** --
the same "deterministic layer, reuse the expensive step only for the
candidates that earn it" principle `portfolio_planner` already
established (PROJECT_CONTEXT.md §13 point 1f).

Two responsibilities, kept separate:

1. **Ingestion** (`ingest_constituent`) -- populates market data,
   financials, corporate filings, news, technical indicators, and
   knowledge embeddings for one company by directly composing the exact
   same service classes `ingestion/tasks.py`'s existing per-domain tasks
   already use (`MarketDataService`, `FinancialStatementService`,
   `CorporateFilingsService`, `NewsIntelligenceService`,
   `TechnicalIntelligenceService`, `KnowledgeLayerService`,
   `ResearchPipelineService`) -- zero duplicated business logic, only a
   new orchestration order. Deliberately does **not** chain into
   `document_intelligence`'s filing-extraction step -- out of this
   version's explicit scope (market data, financials, filings metadata,
   news, technical indicators, knowledge embeddings only), and this
   sandbox's dev filings provider doesn't produce real document links
   anyway (PROJECT_CONTEXT.md §14).

2. **Screening** (`screen`) -- once a batch of constituents has finished
   ingesting, ranks them by a deterministic evidence-completeness score
   computed entirely from data these ingestion steps already wrote (no
   new evidence type, no LLM judgement), marks the strongest `top_n` as
   `is_screened_in`, and enqueues `run_investment_committee` (unchanged,
   `ingestion/tasks.py`) only for those -- resolving the "populate
   Investment Committee outputs... /  only the strongest candidates
   proceed to Investment Committee analysis" tension in the v1.4 request
   by reading the first as "the module is capable of it," gated by the
   second's explicit screening requirement. A committee report already
   fresh (< `COMMITTEE_FRESHNESS_DAYS`, mirroring `portfolio_planner`'s
   own freshness window) is not regenerated on a repeat screen call.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.ai_agents.models import AGENT_CODE_INVESTMENT_COMMITTEE
from nivesh.ai_agents.repository import AgentFindingRepository
from nivesh.companies.models import Company
from nivesh.companies.repository import CompanyRepository, ExchangeRepository
from nivesh.corporate_filings.providers.factory import get_corporate_filings_provider
from nivesh.corporate_filings.repository import (
    CorporateFilingRepository,
    FilingCategoryRepository,
    FilingSourceRepository,
)
from nivesh.corporate_filings.service import CorporateFilingsService
from nivesh.document_intelligence.repository import DocumentExtractionRepository
from nivesh.financials.providers.factory import get_financial_data_provider
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.financials.service import FinancialStatementService
from nivesh.knowledge_layer.providers.factory import get_embedding_provider
from nivesh.knowledge_layer.repository import KnowledgeEmbeddingRepository
from nivesh.knowledge_layer.service import KnowledgeLayerService
from nivesh.market_data.providers.factory import get_market_data_provider
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.market_data.service import MarketDataService
from nivesh.market_universe.models import STATUS_READY, UniverseConstituent
from nivesh.market_universe.repository import UniverseConstituentRepository
from nivesh.news_intelligence.providers.factory import get_news_provider
from nivesh.news_intelligence.repository import NewsArticleRepository
from nivesh.news_intelligence.service import NewsIntelligenceService
from nivesh.research.repository import ResearchDossierRepository
from nivesh.research.service import ResearchPipelineService
from nivesh.technical_intelligence.providers.factory import get_technical_data_provider
from nivesh.technical_intelligence.repository import TechnicalIndicatorRepository
from nivesh.technical_intelligence.service import TechnicalIntelligenceService

logger = logging.getLogger(__name__)

# Documented starting guess, not empirically tuned -- same caveat every
# other threshold constant in this codebase carries (see
# portfolio_planner/service.py's own UNIVERSE_TIER1_LIMIT etc.). Mirrors
# portfolio_planner.service.UNIVERSE_TIER2_CAP by value (not by import,
# to avoid a load-bearing cross-module import of a private-feeling
# constant) so the number of companies this module makes
# committee-eligible lines up with the number portfolio_planner's own
# Tier 2 cap will actually consider.
DEFAULT_SCREEN_TOP_N = 25
COMMITTEE_FRESHNESS_DAYS = 7

# Screening score weights -- deterministic evidence-completeness signals
# only, no LLM judgement. Each component is normalized to [0, 1] before
# weighting. "Depth" components (news/filings/embeddings counts) are
# capped, not just summed, so one company with an unusually large volume
# of news doesn't dominate purely on volume.
_NEWS_DEPTH_CAP = 10
_FILINGS_DEPTH_CAP = 5
_EMBEDDINGS_DEPTH_CAP = 20
_MARKET_DATA_DEPTH_CAP_DAYS = 250  # roughly one trading year
_RECENCY_STALE_DAYS = 14


@dataclass(frozen=True)
class ScreeningComponents:
    market_data: float
    technical_indicators: float
    news: float
    filings: float
    embeddings: float

    @property
    def total(self) -> float:
        return (
            0.30 * self.market_data
            + 0.20 * self.technical_indicators
            + 0.20 * self.news
            + 0.10 * self.filings
            + 0.20 * self.embeddings
        )


class MarketUniverseService:
    def __init__(
        self,
        session: AsyncSession,
        universe_repository: UniverseConstituentRepository,
        company_repository: CompanyRepository,
        exchange_repository: ExchangeRepository,
        ohlcv_repository: HistoricalOHLCVRepository,
        indicator_repository: TechnicalIndicatorRepository,
        statement_repository: FinancialStatementRepository,
        category_repository: FilingCategoryRepository,
        source_repository: FilingSourceRepository,
        filing_repository: CorporateFilingRepository,
        news_repository: NewsArticleRepository,
        embedding_repository: KnowledgeEmbeddingRepository,
        dossier_repository: ResearchDossierRepository,
        finding_repository: AgentFindingRepository,
    ) -> None:
        self._session = session
        self._universe = universe_repository
        self._companies = company_repository
        self._exchanges = exchange_repository
        self._ohlcv = ohlcv_repository
        self._indicators = indicator_repository
        self._statements = statement_repository
        self._categories = category_repository
        self._sources = source_repository
        self._filings = filing_repository
        self._news = news_repository
        self._embeddings = embedding_repository
        self._dossiers = dossier_repository
        self._findings = finding_repository

    async def sync_one(self, index_name: str, symbol: str) -> None:
        """Task-level entrypoint: resolves the tracked constituent row,
        runs the full ingestion pipeline, and records the outcome --
        mirroring `PortfolioPlannerService.generate`'s "never raise, always
        leave a terminal, explained status behind" shape, since a single
        company's ingestion failure (a bad symbol, a provider outage)
        should never take down the rest of the universe sync batch."""
        constituent = await self._universe.get_by_symbol(index_name, symbol)
        if constituent is None:  # pragma: no cover -- defensive, should not happen
            logger.error("universe_constituent_not_found", extra={"symbol": symbol})
            return

        await self._universe.mark_ingesting(constituent)
        try:
            company = await self.ingest_constituent(constituent)
        except Exception as exc:
            logger.exception("universe_constituent_ingestion_failed", extra={"symbol": symbol})
            await self._universe.mark_failed(constituent, reason=str(exc)[:500])
            return
        await self._universe.mark_ready(constituent, company_id=company.id)

    async def ingest_constituent(self, constituent: UniverseConstituent) -> Company:
        """Populates market data, financials, corporate filings, news,
        technical indicators, and knowledge embeddings for one company --
        directly composing the same services the standard per-domain
        Celery tasks use, in the same order `sync_company_market_data`'s
        own auto-chain already establishes (dossier refresh + technical
        indicators follow market data), see module docstring.

        Market data is the one step allowed to raise -- everything else
        (a `Company` row) depends on it having succeeded. Every step
        after that runs independently via `_run_step`: each is caught
        and logged rather than aborting the rest, because these six
        steps have no dependency on each other's success (unlike
        `sync_company_market_data`'s own auto-chain, which only ever
        chains after a *successful* sync). This matters in practice --
        `FinancialStatementService.sync_company_financials` iterates
        every annual/quarterly period the provider returns and aborts
        the whole batch (including periods that would have persisted
        cleanly) the moment any single period fails validation, a
        pre-existing fragility (`financials/validation.py`, shipped
        since v0.3) most likely to bite on a real, recently-published
        quarter with fields the provider hasn't fully populated yet --
        observed live during this version's own verification. Fixing
        that loop's atomicity is out of this version's scope (a
        different, already-shipped module); not letting one already-
        known-flaky step take five independent, unrelated ones down
        with it is squarely this orchestrator's own responsibility."""
        market_data_service = MarketDataService(
            provider=get_market_data_provider(),
            company_repository=self._companies,
            exchange_repository=self._exchanges,
            ohlcv_repository=self._ohlcv,
            corporate_action_repository=CorporateActionRepository(self._session),
        )
        market_result = await market_data_service.sync_company(constituent.symbol)
        company = await self._companies.get_by_id(market_result.company_id)
        assert company is not None  # just upserted above

        indicator_service = TechnicalIntelligenceService(
            provider=get_technical_data_provider(self._ohlcv),
            company_repository=self._companies,
            indicator_repository=self._indicators,
            dossier_repository=self._dossiers,
        )
        await self._run_step(
            "technical_indicators", indicator_service.generate_indicators, constituent.symbol
        )

        dossier_service = ResearchPipelineService(
            company_repository=self._companies,
            dossier_repository=self._dossiers,
            ohlcv_repository=self._ohlcv,
            corporate_action_repository=CorporateActionRepository(self._session),
        )
        await self._run_step("dossier_refresh", dossier_service.refresh_dossier, constituent.symbol)

        financial_service = FinancialStatementService(
            provider=get_financial_data_provider(),
            company_repository=self._companies,
            statement_repository=self._statements,
            dossier_repository=self._dossiers,
        )
        await self._run_step(
            "financials", financial_service.sync_company_financials, constituent.symbol
        )

        filings_service = CorporateFilingsService(
            provider=get_corporate_filings_provider(),
            company_repository=self._companies,
            category_repository=self._categories,
            source_repository=self._sources,
            filing_repository=self._filings,
            dossier_repository=self._dossiers,
        )
        await self._run_step("filings", filings_service.sync_company_filings, constituent.symbol)

        news_service = NewsIntelligenceService(
            provider=get_news_provider(),
            company_repository=self._companies,
            article_repository=self._news,
            dossier_repository=self._dossiers,
        )
        await self._run_step("news", news_service.sync_company_news, constituent.symbol)

        embedding_service = KnowledgeLayerService(
            provider=get_embedding_provider(),
            company_repository=self._companies,
            filing_repository=self._filings,
            extraction_repository=DocumentExtractionRepository(self._session),
            article_repository=self._news,
            dossier_repository=self._dossiers,
            embedding_repository=self._embeddings,
        )
        await self._run_step(
            "embeddings", embedding_service.generate_embeddings, constituent.symbol
        )

        return company

    async def _run_step(
        self, step_name: str, coro_fn: Callable[[str], Awaitable[object]], symbol: str
    ) -> None:
        try:
            await coro_fn(symbol)
        except Exception:
            logger.exception(
                "universe_ingestion_step_failed", extra={"symbol": symbol, "step": step_name}
            )

    async def compute_score(self, company_id: uuid.UUID) -> ScreeningComponents:
        """Pure evidence-completeness scoring over already-ingested data --
        no LLM judgement, no new evidence type. Each candidate must have
        already cleared `portfolio_planner`'s own Tier 1 quorum filter
        (financial statements exist) before this ever runs."""
        summary = await self._ohlcv.get_summary_for_company(company_id)
        bar_count = summary["count"] or 0
        recency_days = (
            (datetime.now(UTC).date() - summary["end_date"]).days
            if summary["end_date"]
            else _RECENCY_STALE_DAYS + 1
        )
        market_data_score = min(bar_count / _MARKET_DATA_DEPTH_CAP_DAYS, 1.0) * (
            1.0 if recency_days <= _RECENCY_STALE_DAYS else 0.5
        )

        indicator_snapshot = await self._indicators.get_latest_snapshot(company_id)
        technical_score = 1.0 if indicator_snapshot else 0.0

        news_articles = await self._news.list_by_company(company_id, limit=_NEWS_DEPTH_CAP)
        news_score = min(len(news_articles) / _NEWS_DEPTH_CAP, 1.0)

        filings = await self._filings.list_by_company(company_id, limit=_FILINGS_DEPTH_CAP)
        filings_score = min(len(filings) / _FILINGS_DEPTH_CAP, 1.0)

        embeddings = await self._embeddings.get_checksums_by_company(company_id)
        embeddings_score = min(len(embeddings) / _EMBEDDINGS_DEPTH_CAP, 1.0)

        return ScreeningComponents(
            market_data=market_data_score,
            technical_indicators=technical_score,
            news=news_score,
            filings=filings_score,
            embeddings=embeddings_score,
        )

    async def screen(
        self, index_name: str, top_n: int = DEFAULT_SCREEN_TOP_N
    ) -> tuple[list[str], list[str]]:
        """Scores every `ready` constituent that has at least one
        financial statement -- the same Tier 1 gate `portfolio_planner`'s
        own `_select_universe` already applies (`FinancialStatement
        Repository.exists_for_company`, mirroring Fundamental Analyst's
        own quorum requirement) -- marks the top `top_n` as
        `is_screened_in`, and returns `(screened_in_symbols,
        committee_needed_symbols)` -- the second list excludes any
        screened-in symbol whose committee report is already fresh, so a
        repeat screen call doesn't redundantly re-spend LLM budget on
        candidates that haven't changed.

        Excluding financial-less candidates here, not just scoring them
        low, matters in practice: a candidate `portfolio_planner` can
        never select (it fails that same Tier 1 gate at request time
        regardless of how good its committee report is) must never reach
        a real Investment Committee run in the first place -- that LLM
        spend can never be recovered by any later portfolio. Found via
        this version's own live verification: before this gate, a
        financials-less real company was screened in on other evidence
        alone and consumed a full committee run it could never benefit
        from."""
        ready = await self._universe.list_by_index(index_name, statuses={STATUS_READY})
        scored: list[tuple[UniverseConstituent, float]] = []
        for constituent in ready:
            if constituent.company_id is None:  # pragma: no cover -- defensive
                continue
            if not await self._statements.exists_for_company(constituent.company_id):
                await self._universe.update_screening(constituent, score=0.0, is_screened_in=False)
                continue
            components = await self.compute_score(constituent.company_id)
            scored.append((constituent, components.total))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        screened_in_symbols: list[str] = []
        committee_needed: list[str] = []
        for rank, (constituent, score) in enumerate(scored):
            is_in = rank < top_n
            await self._universe.update_screening(constituent, score=score, is_screened_in=is_in)
            if not is_in:
                continue
            screened_in_symbols.append(constituent.symbol)
            if await self._needs_committee_run(constituent.company_id):  # type: ignore[arg-type]
                committee_needed.append(constituent.symbol)

        return screened_in_symbols, committee_needed

    async def _needs_committee_run(self, company_id: uuid.UUID) -> bool:
        existing = await self._findings.get_latest(company_id, AGENT_CODE_INVESTMENT_COMMITTEE)
        if existing is None:
            return True
        age = datetime.now(UTC) - existing.updated_at.astimezone(UTC)
        return age >= timedelta(days=COMMITTEE_FRESHNESS_DAYS)

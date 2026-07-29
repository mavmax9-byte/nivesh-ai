"""Technical Intelligence Engine service.

Orchestrates provider fetches (of already-persisted OHLCV bars), validation,
indicator computation, and persistence, then links the results into the
existing Research Dossier as evidence. `SOURCE_TYPE_TECHNICAL_INDICATOR`
had already been reserved (unused) in research/models.py's SourceType
catalog since Sprint 3 specifically for this -- this sprint is the first to
actually populate it, requiring zero changes to research/models.py or
research/schemas.py.

Recompute scope is a **bounded trailing window**, not full company history
(a deliberate v0.6 decision, made over recomputing every indicator across a
company's entire price history on every run): each generation run fetches
only the most recent `LOOKBACK_BARS` OHLCV bars -- comfortably more than
the longest window any indicator here needs (SMA-200), leaving ample margin
for the standard seeding convention recursively defined indicators (EMA,
RSI, MACD, ATR) use (see normalization.py's module docstring). This keeps
the cost of a single generation run bounded and independent of how many
years of history a company has accumulated. Every indicator besides OBV is
a pure function of a fixed trailing window ending on a given date, so
values for dates outside the current window are already correct and would
not change on recompute anyway. OBV is the one exception (a running
cumulative total, not a fixed-window calculation) and is carried forward
explicitly from the last persisted value rather than re-derived from the
window alone -- see normalization.py's `compute_obv`.

ResearchSource's own docstring (research/models.py) already documents that
"technical_indicator" evidence should be referenced as an aggregate date
range with a record count, the same way market_data's OHLCV evidence is --
unlike the discrete, one-row-per-item evidence corporate_filings/
document_intelligence/news_intelligence attach. `_link_to_research_dossier`
follows that existing guidance: one aggregate ResearchSource row per
generation run, not one per indicator value.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.research.models import SOURCE_TYPE_TECHNICAL_INDICATOR
from nivesh.research.repository import ResearchDossierRepository
from nivesh.technical_intelligence.models import INDICATOR_OBV, TechnicalIndicator
from nivesh.technical_intelligence.normalization import (
    EMA_PERIODS,
    SMA_PERIODS,
    ComputedIndicatorPoint,
    bars_to_frame,
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_macd,
    compute_obv,
    compute_rsi,
    compute_sma,
    compute_volume_sma,
)
from nivesh.technical_intelligence.providers.base import TechnicalDataProvider
from nivesh.technical_intelligence.repository import TechnicalIndicatorRepository
from nivesh.technical_intelligence.validation import (
    validate_no_duplicate_timestamps,
    validate_no_missing_values,
    validate_prices,
    validate_sufficient_history,
    validate_volumes,
)

logger = logging.getLogger(__name__)

# Comfortably more than the longest window any indicator here needs
# (SMA-200), leaving generous margin for recursive-indicator seeding.
LOOKBACK_BARS = 300
PROVIDER_SOURCE_TABLE = "technical_indicators"
EVENT_TYPE_INDICATORS_GENERATED = "technical_indicators_generated"


@dataclass(frozen=True)
class IndicatorGenerationResult:
    company_id: uuid.UUID
    symbol: str
    indicators_generated: int
    trading_date_start: date | None
    trading_date_end: date | None


class TechnicalIntelligenceService:
    def __init__(
        self,
        provider: TechnicalDataProvider,
        company_repository: CompanyRepository,
        indicator_repository: TechnicalIndicatorRepository,
        dossier_repository: ResearchDossierRepository,
    ) -> None:
        self._provider = provider
        self._companies = company_repository
        self._indicators = indicator_repository
        self._dossiers = dossier_repository

    async def generate_indicators(self, symbol: str) -> IndicatorGenerationResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        bars = await self._provider.get_price_history(company.id, limit=LOOKBACK_BARS)
        validate_sufficient_history(bars)
        validate_no_missing_values(bars)
        validate_no_duplicate_timestamps(bars)
        validate_prices(bars)
        validate_volumes(bars)

        frame = bars_to_frame(bars)

        points: list[ComputedIndicatorPoint] = []
        for period in SMA_PERIODS:
            points += compute_sma(frame, period)
        for period in EMA_PERIODS:
            points += compute_ema(frame, period)
        points += compute_rsi(frame)
        for series in compute_macd(frame):
            points += series
        for series in compute_bollinger_bands(frame):
            points += series
        points += compute_atr(frame)
        points += compute_volume_sma(frame)

        last_obv = await self._indicators.get_last_indicator_value(company.id, INDICATOR_OBV)
        starting_value = float(last_obv.indicator_value) if last_obv is not None else 0.0
        starting_date = last_obv.trading_date if last_obv is not None else None
        points += compute_obv(frame, starting_value, starting_date)

        calculation_timestamp = datetime.now(UTC)
        rows = [
            {
                "company_id": company.id,
                "trading_date": point.trading_date,
                "indicator_name": point.indicator_name,
                "indicator_parameters": point.indicator_parameters,
                "indicator_value": point.indicator_value,
                "calculation_timestamp": calculation_timestamp,
            }
            for point in points
        ]

        await self._indicators.bulk_upsert(rows)
        await self._link_to_research_dossier(company.id, company.symbol, rows)

        trading_dates: list[date] = [point.trading_date for point in points]
        return IndicatorGenerationResult(
            company_id=company.id,
            symbol=company.symbol,
            indicators_generated=len(rows),
            trading_date_start=min(trading_dates) if trading_dates else None,
            trading_date_end=max(trading_dates) if trading_dates else None,
        )

    async def get_latest_indicators(self, symbol: str) -> list[TechnicalIndicator]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._indicators.get_latest_snapshot(company.id)

    async def get_indicator_history(
        self, symbol: str, limit: int = 200, offset: int = 0
    ) -> list[TechnicalIndicator]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._indicators.get_history(company.id, limit=limit, offset=offset)

    async def get_indicators_by_name(
        self, symbol: str, indicator_name: str, limit: int = 200, offset: int = 0
    ) -> list[TechnicalIndicator]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._indicators.get_history_by_indicator(
            company.id, indicator_name, limit=limit, offset=offset
        )

    # -- internals -----------------------------------------------------

    async def _link_to_research_dossier(
        self, company_id: uuid.UUID, symbol: str, rows: list[dict]
    ) -> None:
        """Records a newly persisted generation run as one aggregate
        Research Dossier evidence row -- see module docstring for why
        technical indicators are linked as an aggregate range rather than
        one row per value.

        Sources are attached to the current research version if one
        already exists; version numbering itself stays owned by
        ResearchPipelineService, so this never creates or bumps a research
        version -- only adds evidence to one that already exists.
        """
        if not rows:
            return

        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "technical_indicators_generated_before_research_version",
                extra={"symbol": symbol, "indicator_count": len(rows)},
            )
            return

        trading_dates: list[date] = [row["trading_date"] for row in rows]
        source_rows = [
            {
                "dossier_id": dossier.id,
                "version_id": latest_version.id,
                "source_type": SOURCE_TYPE_TECHNICAL_INDICATOR,
                "reference_table": PROVIDER_SOURCE_TABLE,
                "reference_id": None,
                "range_start": min(trading_dates),
                "range_end": max(trading_dates),
                "record_count": len(rows),
            }
        ]
        await self._dossiers.bulk_create_sources(source_rows)
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_INDICATORS_GENERATED,
            description=f"{len(rows)} technical indicator value(s) generated for '{symbol}'.",
            version_id=latest_version.id,
        )
        await self._indicators.commit()

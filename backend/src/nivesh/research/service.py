"""Research Pipeline service.

Transforms already-validated market data (from MarketDataService, Sprint 1)
into a versioned Company Research Dossier. No AI reasoning, no LLM calls, no
generated summaries -- every value here is either copied directly from
already-persisted rows or computed deterministically from them (counts,
min/max dates, arithmetic deltas). This is the "collecting, organizing,
versioning and enriching" stage; interpretation is a later sprint's concern.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.market_data.repository import CorporateActionRepository, HistoricalOHLCVRepository
from nivesh.research.change_summary import build_change_summary
from nivesh.research.models import (
    EVENT_TYPE_VERSION_CREATED,
    SOURCE_TYPE_CORPORATE_ACTION,
    SOURCE_TYPE_MARKET_DATA,
    TRIGGERED_BY_MARKET_DATA_SYNC,
    ResearchTimeline,
    ResearchVersion,
)
from nivesh.research.repository import ResearchDossierRepository

PROVIDER_SOURCE_TABLE_OHLCV = "historical_ohlcv"
PROVIDER_SOURCE_TABLE_CORPORATE_ACTIONS = "corporate_actions"


@dataclass(frozen=True)
class RefreshResult:
    dossier_id: uuid.UUID
    company_id: uuid.UUID
    symbol: str
    changed: bool
    version_number: int


@dataclass(frozen=True)
class DossierOverview:
    symbol: str
    current_version_number: int
    last_refreshed_at: datetime | None
    latest_version: ResearchVersion | None
    recent_timeline: list[ResearchTimeline] = field(default_factory=list)
    evidence_counts: dict[str, int] = field(default_factory=dict)


class ResearchPipelineService:
    def __init__(
        self,
        company_repository: CompanyRepository,
        dossier_repository: ResearchDossierRepository,
        ohlcv_repository: HistoricalOHLCVRepository,
        corporate_action_repository: CorporateActionRepository,
    ) -> None:
        self._companies = company_repository
        self._dossiers = dossier_repository
        self._ohlcv = ohlcv_repository
        self._corporate_actions = corporate_action_repository

    async def refresh_dossier(self, symbol: str) -> RefreshResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        dossier = await self._dossiers.get_or_create_dossier(company.id)

        ohlcv_summary = await self._ohlcv.get_summary_for_company(company.id)
        latest_bars = await self._ohlcv.list_for_company(company.id, limit=1)
        latest_bar = latest_bars[0] if latest_bars else None

        corporate_actions = await self._corporate_actions.list_for_company(company.id)
        latest_action_date = max((a.ex_date for a in corporate_actions), default=None)

        new_watermark = {
            "price_bar_count": ohlcv_summary["count"],
            "latest_trade_date": ohlcv_summary["end_date"].isoformat()
            if ohlcv_summary["end_date"]
            else None,
            "corporate_action_count": len(corporate_actions),
        }

        if dossier.last_market_data_watermark == new_watermark:
            return RefreshResult(
                dossier_id=dossier.id,
                company_id=company.id,
                symbol=company.symbol,
                changed=False,
                version_number=dossier.current_version_number,
            )

        next_version_number = dossier.current_version_number + 1
        change_summary = build_change_summary(dossier.last_market_data_watermark, new_watermark)

        version = await self._dossiers.create_version(
            dossier_id=dossier.id,
            version_number=next_version_number,
            triggered_by=TRIGGERED_BY_MARKET_DATA_SYNC,
            change_summary=change_summary,
        )

        await self._dossiers.create_snapshot(
            version_id=version.id,
            company_id=company.id,
            sector=company.sector,
            industry=company.industry,
            latest_price=latest_bar.close if latest_bar else None,
            latest_trade_date=latest_bar.trade_date if latest_bar else None,
            price_bar_count=ohlcv_summary["count"],
            price_history_start=ohlcv_summary["start_date"],
            price_history_end=ohlcv_summary["end_date"],
            corporate_action_count=len(corporate_actions),
            latest_corporate_action_date=latest_action_date,
        )

        source_rows: list[dict] = []
        if ohlcv_summary["count"]:
            source_rows.append(
                {
                    "dossier_id": dossier.id,
                    "version_id": version.id,
                    "source_type": SOURCE_TYPE_MARKET_DATA,
                    "reference_table": PROVIDER_SOURCE_TABLE_OHLCV,
                    "reference_id": None,
                    "range_start": ohlcv_summary["start_date"],
                    "range_end": ohlcv_summary["end_date"],
                    "record_count": ohlcv_summary["count"],
                }
            )
        for action in corporate_actions:
            source_rows.append(
                {
                    "dossier_id": dossier.id,
                    "version_id": version.id,
                    "source_type": SOURCE_TYPE_CORPORATE_ACTION,
                    "reference_table": PROVIDER_SOURCE_TABLE_CORPORATE_ACTIONS,
                    "reference_id": action.id,
                    "range_start": action.ex_date,
                    "range_end": action.ex_date,
                    "record_count": 1,
                }
            )
        await self._dossiers.bulk_create_sources(source_rows)

        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company.id,
            event_type=EVENT_TYPE_VERSION_CREATED,
            description=change_summary,
            version_id=version.id,
        )

        await self._dossiers.finalize_version(
            dossier=dossier, version_number=next_version_number, watermark=new_watermark
        )

        return RefreshResult(
            dossier_id=dossier.id,
            company_id=company.id,
            symbol=company.symbol,
            changed=True,
            version_number=next_version_number,
        )

    async def get_dossier_overview(self, symbol: str) -> DossierOverview:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        dossier = await self._dossiers.get_by_company_id(company.id)
        if dossier is None:
            raise NotFoundError(f"No research dossier exists yet for symbol '{symbol}'")

        latest_version = await self._dossiers.get_latest_version(dossier.id)
        timeline = await self._dossiers.get_recent_timeline(dossier.id, limit=20)
        evidence_counts = (
            await self._dossiers.get_evidence_counts(latest_version.id) if latest_version else {}
        )

        return DossierOverview(
            symbol=company.symbol,
            current_version_number=dossier.current_version_number,
            last_refreshed_at=dossier.last_refreshed_at,
            latest_version=latest_version,
            recent_timeline=timeline,
            evidence_counts=evidence_counts,
        )

    async def get_latest_version(self, symbol: str) -> ResearchVersion:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        dossier = await self._dossiers.get_by_company_id(company.id)
        if dossier is None:
            raise NotFoundError(f"No research dossier exists yet for symbol '{symbol}'")

        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            raise NotFoundError(f"No research version exists yet for symbol '{symbol}'")
        return latest_version

    async def get_version_history(
        self, symbol: str, limit: int = 50, offset: int = 0
    ) -> list[ResearchVersion]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        dossier = await self._dossiers.get_by_company_id(company.id)
        if dossier is None:
            raise NotFoundError(f"No research dossier exists yet for symbol '{symbol}'")

        return await self._dossiers.get_version_history(dossier.id, limit=limit, offset=offset)

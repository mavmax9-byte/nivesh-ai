"""Financial Statements Engine service.

Orchestrates provider fetches, validation, normalization, and persistence,
then links the results into the existing Research Dossier as evidence --
`SOURCE_TYPE_FINANCIAL_DATA` was reserved for exactly this in
research/models.py ("later sprints... extend this catalog, not the
schema"). No AI, no LLM calls: every value here is either copied directly
from a provider-sourced statement or computed with plain arithmetic from
already-validated figures (FinancialRatio, QuarterlyResult growth deltas).
"""

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from nivesh.companies.repository import CompanyRepository
from nivesh.core.exceptions import NotFoundError
from nivesh.financials.models import PERIOD_TYPE_ANNUAL, PERIOD_TYPE_QUARTERLY, FinancialStatement
from nivesh.financials.normalization import (
    BALANCE_SHEET_FIELDS,
    CASH_FLOW_FIELDS,
    PROFIT_AND_LOSS_FIELDS,
    extract_fields,
    normalize_balance_sheet,
    normalize_cash_flow,
    normalize_profit_and_loss,
    normalize_statement,
)
from nivesh.financials.providers.base import FinancialDataProvider, ProviderFinancialStatement
from nivesh.financials.repository import FinancialStatementRepository
from nivesh.financials.validation import (
    is_duplicate_statement,
    validate_accounting_equation,
    validate_balance_sheet_fields,
    validate_cash_flow_fields,
    validate_currency,
    validate_profit_and_loss_fields,
    validate_reporting_period,
)
from nivesh.research.models import SOURCE_TYPE_FINANCIAL_DATA
from nivesh.research.repository import ResearchDossierRepository

logger = logging.getLogger(__name__)

PROVIDER_SOURCE_NAME = "yfinance"
PROVIDER_SOURCE_TABLE = "financial_statements"
EVENT_TYPE_FINANCIALS_SYNCED = "financials_synced"


@dataclass(frozen=True)
class FinancialSyncResult:
    company_id: uuid.UUID
    symbol: str
    statements_synced: int
    statements_unchanged: int


@dataclass(frozen=True)
class FinancialsOverview:
    symbol: str
    latest_annual: FinancialStatement | None
    latest_quarterly: FinancialStatement | None


def _safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator).quantize(Decimal("0.0001"))


def _safe_percentage(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    ratio = _safe_ratio(numerator, denominator)
    return None if ratio is None else (ratio * 100).quantize(Decimal("0.0001"))


def _growth_pct(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / abs(previous) * 100).quantize(Decimal("0.0001"))


def _pl_field(statement: FinancialStatement | None, field_name: str) -> Decimal | None:
    if statement is None or statement.profit_and_loss is None:
        return None
    return getattr(statement.profit_and_loss, field_name)


class FinancialStatementService:
    def __init__(
        self,
        provider: FinancialDataProvider,
        company_repository: CompanyRepository,
        statement_repository: FinancialStatementRepository,
        dossier_repository: ResearchDossierRepository,
    ) -> None:
        self._provider = provider
        self._companies = company_repository
        self._statements = statement_repository
        self._dossiers = dossier_repository

    async def sync_company_financials(self, symbol: str) -> FinancialSyncResult:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        annual = await self._provider.get_annual_statements(symbol)
        quarterly = await self._provider.get_quarterly_statements(symbol)

        synced_statements: list[FinancialStatement] = []
        unchanged = 0
        expected_currency: str | None = None

        for provider_statement in [*annual, *quarterly]:
            statement, was_new = await self._persist_statement(
                company.id, provider_statement, expected_currency
            )
            expected_currency = provider_statement.currency
            if was_new:
                synced_statements.append(statement)
            else:
                unchanged += 1

        await self._link_to_research_dossier(company.id, company.symbol, synced_statements)

        return FinancialSyncResult(
            company_id=company.id,
            symbol=company.symbol,
            statements_synced=len(synced_statements),
            statements_unchanged=unchanged,
        )

    async def get_overview(self, symbol: str) -> FinancialsOverview:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")

        latest_annual = await self._statements.list_latest_statements(
            company.id, PERIOD_TYPE_ANNUAL, limit=1
        )
        latest_quarterly = await self._statements.list_latest_statements(
            company.id, PERIOD_TYPE_QUARTERLY, limit=1
        )
        return FinancialsOverview(
            symbol=company.symbol,
            latest_annual=latest_annual[0] if latest_annual else None,
            latest_quarterly=latest_quarterly[0] if latest_quarterly else None,
        )

    async def get_annual_statements(self, symbol: str, limit: int = 8) -> list[FinancialStatement]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._statements.list_latest_statements(
            company.id, PERIOD_TYPE_ANNUAL, limit=limit
        )

    async def get_quarterly_statements(
        self, symbol: str, limit: int = 8
    ) -> list[FinancialStatement]:
        company = await self._companies.get_by_symbol(symbol)
        if company is None:
            raise NotFoundError(f"No company found with symbol '{symbol}'")
        return await self._statements.list_latest_statements(
            company.id, PERIOD_TYPE_QUARTERLY, limit=limit
        )

    # -- internals ---------------------------------------------------

    async def _persist_statement(
        self,
        company_id: uuid.UUID,
        provider_statement: ProviderFinancialStatement,
        expected_currency: str | None,
    ) -> tuple[FinancialStatement, bool]:
        validate_reporting_period(
            period_type=provider_statement.period_type,
            fiscal_year=provider_statement.fiscal_year,
            fiscal_period=provider_statement.fiscal_period,
            period_end_date_year=provider_statement.period_end_date.year,
        )
        validate_currency(provider_statement.currency, expected_currency)

        balance_sheet_data = normalize_balance_sheet(provider_statement)
        profit_and_loss_data = normalize_profit_and_loss(provider_statement)
        cash_flow_data = normalize_cash_flow(provider_statement)

        validate_balance_sheet_fields(balance_sheet_data)
        validate_profit_and_loss_fields(profit_and_loss_data)
        validate_cash_flow_fields(cash_flow_data)
        validate_accounting_equation(
            balance_sheet_data["total_assets"],
            balance_sheet_data["total_liabilities"],
            balance_sheet_data["total_equity"],
        )

        existing = await self._statements.get_latest_statement(
            company_id,
            provider_statement.period_type,
            provider_statement.fiscal_year,
            provider_statement.fiscal_period,
        )
        if existing is not None and self._is_unchanged(
            existing, balance_sheet_data, profit_and_loss_data, cash_flow_data
        ):
            return existing, False

        next_version = (existing.version + 1) if existing is not None else 1
        statement_row = normalize_statement(company_id, provider_statement, PROVIDER_SOURCE_NAME)

        statement = await self._statements.create_statement(**statement_row, version=next_version)
        await self._statements.create_balance_sheet(statement.id, balance_sheet_data)
        await self._statements.create_profit_and_loss(statement.id, profit_and_loss_data)
        await self._statements.create_cash_flow(statement.id, cash_flow_data)

        if provider_statement.period_type == PERIOD_TYPE_QUARTERLY:
            await self._create_quarterly_result(company_id, statement, profit_and_loss_data)

        await self._create_financial_ratio(
            statement, balance_sheet_data, profit_and_loss_data, cash_flow_data
        )

        statement = await self._statements.commit_statement(statement)
        return statement, True

    @staticmethod
    def _is_unchanged(
        existing: FinancialStatement,
        balance_sheet_data: dict,
        profit_and_loss_data: dict,
        cash_flow_data: dict,
    ) -> bool:
        if (
            existing.balance_sheet is None
            or existing.profit_and_loss is None
            or existing.cash_flow is None
        ):
            return False

        incoming_signature = {
            **extract_fields(balance_sheet_data, BALANCE_SHEET_FIELDS),
            **extract_fields(profit_and_loss_data, PROFIT_AND_LOSS_FIELDS),
            **extract_fields(cash_flow_data, CASH_FLOW_FIELDS),
        }
        existing_signature = {
            **extract_fields(existing.balance_sheet, BALANCE_SHEET_FIELDS),
            **extract_fields(existing.profit_and_loss, PROFIT_AND_LOSS_FIELDS),
            **extract_fields(existing.cash_flow, CASH_FLOW_FIELDS),
        }
        return is_duplicate_statement(existing_signature, incoming_signature)

    async def _create_quarterly_result(
        self, company_id: uuid.UUID, statement: FinancialStatement, profit_and_loss_data: dict
    ) -> None:
        revenue = profit_and_loss_data["total_revenue"]
        net_profit = profit_and_loss_data["net_income"]
        operating_income = profit_and_loss_data.get("operating_income")
        eps = profit_and_loss_data.get("eps_diluted") or profit_and_loss_data.get("eps_basic")

        previous_quarter = await self._statements.get_latest_statement_before(
            company_id, PERIOD_TYPE_QUARTERLY, statement.period_end_date
        )
        same_quarter_last_year = await self._statements.get_latest_statement(
            company_id, PERIOD_TYPE_QUARTERLY, statement.fiscal_year - 1, statement.fiscal_period
        )

        await self._statements.create_quarterly_result(
            statement.id,
            {
                "revenue": revenue,
                "net_profit": net_profit,
                "eps": eps,
                "operating_margin": _safe_percentage(operating_income, revenue),
                "net_profit_margin": _safe_percentage(net_profit, revenue),
                "qoq_revenue_growth_pct": _growth_pct(
                    revenue, _pl_field(previous_quarter, "total_revenue")
                ),
                "yoy_revenue_growth_pct": _growth_pct(
                    revenue, _pl_field(same_quarter_last_year, "total_revenue")
                ),
                "qoq_net_profit_growth_pct": _growth_pct(
                    net_profit, _pl_field(previous_quarter, "net_income")
                ),
                "yoy_net_profit_growth_pct": _growth_pct(
                    net_profit, _pl_field(same_quarter_last_year, "net_income")
                ),
            },
        )

    async def _create_financial_ratio(
        self,
        statement: FinancialStatement,
        balance_sheet_data: dict,
        profit_and_loss_data: dict,
        cash_flow_data: dict,
    ) -> None:
        total_assets = balance_sheet_data["total_assets"]
        total_equity = balance_sheet_data["total_equity"]
        current_assets = balance_sheet_data.get("current_assets")
        current_liabilities = balance_sheet_data.get("current_liabilities")
        total_debt = balance_sheet_data.get("total_debt")
        total_revenue = profit_and_loss_data["total_revenue"]
        net_income = profit_and_loss_data["net_income"]
        operating_income = profit_and_loss_data.get("operating_income")
        interest_expense = profit_and_loss_data.get("interest_expense")

        await self._statements.create_financial_ratio(
            statement.id,
            {
                "current_ratio": _safe_ratio(current_assets, current_liabilities),
                "debt_to_equity": _safe_ratio(total_debt, total_equity),
                "net_profit_margin": _safe_percentage(net_income, total_revenue),
                "operating_margin": _safe_percentage(operating_income, total_revenue),
                "return_on_equity": _safe_percentage(net_income, total_equity),
                "return_on_assets": _safe_percentage(net_income, total_assets),
                "asset_turnover": _safe_ratio(total_revenue, total_assets),
                "interest_coverage_ratio": _safe_ratio(operating_income, interest_expense),
            },
        )

    async def _link_to_research_dossier(
        self, company_id: uuid.UUID, symbol: str, synced_statements: list[FinancialStatement]
    ) -> None:
        """Records newly synced statements as Research Dossier evidence.

        `SOURCE_TYPE_FINANCIAL_DATA` was reserved on ResearchSource
        specifically for this. Sources are attached to the current research
        version if one already exists; version numbering itself stays owned
        by ResearchPipelineService, so this never creates or bumps a
        research version -- only adds evidence to one that already exists.
        """
        if not synced_statements:
            return

        dossier = await self._dossiers.get_or_create_dossier(company_id)
        latest_version = await self._dossiers.get_latest_version(dossier.id)
        if latest_version is None:
            logger.info(
                "financial_statements_synced_before_research_version",
                extra={"symbol": symbol, "statement_count": len(synced_statements)},
            )
            return

        source_rows = [
            {
                "dossier_id": dossier.id,
                "version_id": latest_version.id,
                "source_type": SOURCE_TYPE_FINANCIAL_DATA,
                "reference_table": PROVIDER_SOURCE_TABLE,
                "reference_id": statement.id,
                "range_start": statement.period_end_date,
                "range_end": statement.period_end_date,
                "record_count": 1,
            }
            for statement in synced_statements
        ]
        await self._dossiers.bulk_create_sources(source_rows)
        await self._dossiers.create_timeline_event(
            dossier_id=dossier.id,
            company_id=company_id,
            event_type=EVENT_TYPE_FINANCIALS_SYNCED,
            description=f"{len(synced_statements)} financial statement(s) synced for '{symbol}'.",
            version_id=latest_version.id,
        )
        await self._statements.commit()

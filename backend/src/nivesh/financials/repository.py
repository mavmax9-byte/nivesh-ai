"""Financial Statements Engine data-access layer.

`FinancialStatement` is treated as an aggregate root, the same way
`CompanyResearchDossier` is in research/repository.py: a statement's
balance sheet, profit & loss, cash flow, (optional) quarterly result, and
ratio must all be written together or not at all, so every write method
below uses `flush()` (visible within the transaction, not yet durable) and
only `commit_statement` -- the last step of persisting one statement --
actually commits. This is the same deliberate exception to the
"each repository method commits its own write" convention used elsewhere
(companies, market_data), for the same reason: a partially-written
statement would be exactly the kind of broken history the versioning model
rules out.

Financial statements are themselves immutable once written, exactly like
ResearchVersion: a restated period is never edited, only inserted as a new
`version` row for the same (company, period_type, fiscal_year,
fiscal_period).
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivesh.financials.models import (
    BalanceSheet,
    CashFlowStatement,
    FinancialRatio,
    FinancialStatement,
    ProfitAndLoss,
    QuarterlyResult,
)

_DETAIL_OPTIONS = (
    selectinload(FinancialStatement.balance_sheet),
    selectinload(FinancialStatement.profit_and_loss),
    selectinload(FinancialStatement.cash_flow),
    selectinload(FinancialStatement.quarterly_result),
    selectinload(FinancialStatement.ratio),
)


class FinancialStatementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -------------------------------------------------------

    async def get_by_id(self, statement_id: uuid.UUID) -> FinancialStatement | None:
        """Added for ai_agents' Valuation Analyst (v1.0): retrieval_engine's
        evidence items carry a `financial_statement`'s id but not its
        detail rows (eps_basic etc.), so the agent resolves the id of its
        highest-relevance financial_statement evidence item back to the
        full statement (with profit_and_loss eager-loaded) to compute a
        real P/E ratio -- see agents/valuation/ratios.py."""
        result = await self._session.execute(
            select(FinancialStatement)
            .options(*_DETAIL_OPTIONS)
            .where(FinancialStatement.id == statement_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_statement(
        self, company_id: uuid.UUID, period_type: str, fiscal_year: int, fiscal_period: str
    ) -> FinancialStatement | None:
        result = await self._session.execute(
            select(FinancialStatement)
            .options(*_DETAIL_OPTIONS)
            .where(
                FinancialStatement.company_id == company_id,
                FinancialStatement.period_type == period_type,
                FinancialStatement.fiscal_year == fiscal_year,
                FinancialStatement.fiscal_period == fiscal_period,
            )
            .order_by(FinancialStatement.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_statement_before(
        self, company_id: uuid.UUID, period_type: str, before: date
    ) -> FinancialStatement | None:
        """Most recent statement of this period_type strictly before a
        given period end -- used to compute quarter-over-quarter deltas."""
        result = await self._session.execute(
            select(FinancialStatement)
            .options(selectinload(FinancialStatement.profit_and_loss))
            .where(
                FinancialStatement.company_id == company_id,
                FinancialStatement.period_type == period_type,
                FinancialStatement.period_end_date < before,
            )
            .order_by(FinancialStatement.period_end_date.desc(), FinancialStatement.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_latest_statements(
        self, company_id: uuid.UUID, period_type: str, limit: int = 8
    ) -> list[FinancialStatement]:
        """The current (highest-version) statement for each distinct
        reporting period, most recent period first.

        Uses Postgres `DISTINCT ON`, consistent with this project's other
        Postgres-specific persistence code (`ON CONFLICT` upserts in
        market_data/repository.py) -- `Select.distinct(*cols)` compiles to
        `DISTINCT ON (cols)` on this dialect, provided the leading ORDER BY
        columns match, which they do here.
        """
        result = await self._session.execute(
            select(FinancialStatement)
            .options(*_DETAIL_OPTIONS)
            .distinct(FinancialStatement.period_end_date)
            .where(
                FinancialStatement.company_id == company_id,
                FinancialStatement.period_type == period_type,
            )
            .order_by(FinancialStatement.period_end_date.desc(), FinancialStatement.version.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # -- writes (flush only, except commit_statement) -----------------

    async def create_statement(
        self,
        *,
        company_id: uuid.UUID,
        period_type: str,
        fiscal_year: int,
        fiscal_period: str,
        period_end_date: date,
        currency: str,
        version: int,
        source: str,
    ) -> FinancialStatement:
        statement = FinancialStatement(
            company_id=company_id,
            period_type=period_type,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            period_end_date=period_end_date,
            currency=currency,
            version=version,
            source=source,
        )
        self._session.add(statement)
        await self._session.flush()
        return statement

    async def create_balance_sheet(
        self, financial_statement_id: uuid.UUID, data: dict
    ) -> BalanceSheet:
        balance_sheet = BalanceSheet(financial_statement_id=financial_statement_id, **data)
        self._session.add(balance_sheet)
        await self._session.flush()
        return balance_sheet

    async def create_profit_and_loss(
        self, financial_statement_id: uuid.UUID, data: dict
    ) -> ProfitAndLoss:
        profit_and_loss = ProfitAndLoss(financial_statement_id=financial_statement_id, **data)
        self._session.add(profit_and_loss)
        await self._session.flush()
        return profit_and_loss

    async def create_cash_flow(
        self, financial_statement_id: uuid.UUID, data: dict
    ) -> CashFlowStatement:
        cash_flow = CashFlowStatement(financial_statement_id=financial_statement_id, **data)
        self._session.add(cash_flow)
        await self._session.flush()
        return cash_flow

    async def create_quarterly_result(
        self, financial_statement_id: uuid.UUID, data: dict
    ) -> QuarterlyResult:
        quarterly_result = QuarterlyResult(financial_statement_id=financial_statement_id, **data)
        self._session.add(quarterly_result)
        await self._session.flush()
        return quarterly_result

    async def create_financial_ratio(
        self, financial_statement_id: uuid.UUID, data: dict
    ) -> FinancialRatio:
        ratio = FinancialRatio(financial_statement_id=financial_statement_id, **data)
        self._session.add(ratio)
        await self._session.flush()
        return ratio

    async def commit_statement(self, statement: FinancialStatement) -> FinancialStatement:
        """Commits the whole write sequence for one statement -- the one
        write in this repository that is not just a flush."""
        await self._session.commit()
        await self._session.refresh(
            statement,
            attribute_names=[
                "balance_sheet",
                "profit_and_loss",
                "cash_flow",
                "quarterly_result",
                "ratio",
            ],
        )
        return statement

    async def commit(self) -> None:
        """Commits whatever is pending on this repository's session.

        Used by FinancialStatementService to durably persist Research
        Dossier evidence rows written through ResearchDossierRepository's
        flush-only methods on this same shared session -- see
        FinancialStatementService._link_to_research_dossier.
        """
        await self._session.commit()

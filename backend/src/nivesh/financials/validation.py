"""Pure validation rules for provider-sourced financial statement data.

No I/O, no side effects -- kept separate from FinancialStatementService so
the rules are independently testable and reusable regardless of which
provider or which service method needs them, mirroring
market_data/validation.py's separation.
"""

from decimal import Decimal

from fastapi import status

from nivesh.core.exceptions import NiveshError
from nivesh.financials.models import (
    FISCAL_PERIOD_FULL_YEAR,
    FISCAL_PERIOD_Q1,
    FISCAL_PERIOD_Q2,
    FISCAL_PERIOD_Q3,
    FISCAL_PERIOD_Q4,
    PERIOD_TYPE_ANNUAL,
    PERIOD_TYPE_QUARTERLY,
)

VALID_PERIOD_TYPES = {PERIOD_TYPE_ANNUAL, PERIOD_TYPE_QUARTERLY}
VALID_QUARTERLY_FISCAL_PERIODS = {
    FISCAL_PERIOD_Q1,
    FISCAL_PERIOD_Q2,
    FISCAL_PERIOD_Q3,
    FISCAL_PERIOD_Q4,
}
MIN_FISCAL_YEAR = 1990
# Relative tolerance for Assets = Liabilities + Equity -- absorbs rounding
# and minority-interest lines this schema does not model as separate fields.
ACCOUNTING_EQUATION_TOLERANCE = Decimal("0.02")


class InvalidFinancialDataError(NiveshError):
    """Raised when provider-sourced financial data fails a validation rule
    that should halt persistence of that statement."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_FINANCIAL_DATA"


def validate_reporting_period(
    *, period_type: str, fiscal_year: int, fiscal_period: str, period_end_date_year: int
) -> None:
    if period_type not in VALID_PERIOD_TYPES:
        raise InvalidFinancialDataError(f"Unknown period_type '{period_type}'.")

    if period_type == PERIOD_TYPE_ANNUAL and fiscal_period != FISCAL_PERIOD_FULL_YEAR:
        raise InvalidFinancialDataError(
            f"Annual statements must use fiscal_period '{FISCAL_PERIOD_FULL_YEAR}', "
            f"got '{fiscal_period}'."
        )
    if period_type == PERIOD_TYPE_QUARTERLY and fiscal_period not in VALID_QUARTERLY_FISCAL_PERIODS:
        raise InvalidFinancialDataError(
            f"Quarterly statements must use one of {sorted(VALID_QUARTERLY_FISCAL_PERIODS)}, "
            f"got '{fiscal_period}'."
        )

    if fiscal_year < MIN_FISCAL_YEAR:
        raise InvalidFinancialDataError(f"fiscal_year {fiscal_year} is implausibly old.")
    if abs(fiscal_year - period_end_date_year) > 1:
        raise InvalidFinancialDataError(
            f"fiscal_year {fiscal_year} is inconsistent with period end year "
            f"{period_end_date_year}."
        )


def validate_currency(currency: str, expected_currency: str | None = None) -> None:
    if not currency or len(currency) != 3 or not currency.isalpha():
        raise InvalidFinancialDataError(f"'{currency}' is not a valid ISO 4217 currency code.")
    if expected_currency is not None and currency.upper() != expected_currency.upper():
        raise InvalidFinancialDataError(
            f"Currency '{currency}' is inconsistent with prior statements reported in "
            f"'{expected_currency}'."
        )


def validate_balance_sheet_fields(data: dict) -> None:
    for field in ("total_assets", "total_liabilities", "total_equity"):
        if data.get(field) is None:
            raise InvalidFinancialDataError(f"Balance sheet is missing required field '{field}'.")


def validate_profit_and_loss_fields(data: dict) -> None:
    for field in ("total_revenue", "net_income"):
        if data.get(field) is None:
            raise InvalidFinancialDataError(
                f"Profit & loss statement is missing required field '{field}'."
            )


def validate_cash_flow_fields(data: dict) -> None:
    if data.get("operating_cash_flow") is None:
        raise InvalidFinancialDataError(
            "Cash flow statement is missing required field 'operating_cash_flow'."
        )


def validate_accounting_equation(
    total_assets: Decimal | None,
    total_liabilities: Decimal | None,
    total_equity: Decimal | None,
) -> None:
    """Assets = Liabilities + Equity, within a relative tolerance.

    Applies only when all three figures are present -- missing figures are
    `validate_balance_sheet_fields`'s concern, not this one's.
    """
    if total_assets is None or total_liabilities is None or total_equity is None:
        return

    difference = abs(total_assets - (total_liabilities + total_equity))
    if total_assets == 0:
        if difference != 0:
            raise InvalidFinancialDataError(
                "Balance sheet fails the accounting equation: assets are zero but "
                "liabilities + equity are not."
            )
        return

    relative_difference = difference / abs(total_assets)
    if relative_difference > ACCOUNTING_EQUATION_TOLERANCE:
        raise InvalidFinancialDataError(
            f"Balance sheet fails the accounting equation: assets ({total_assets}) != "
            f"liabilities + equity ({total_liabilities + total_equity})."
        )


def is_duplicate_statement(existing: dict, incoming: dict) -> bool:
    """True when incoming figures are identical to the latest stored
    version for this period -- re-syncing unchanged provider data should be
    a no-op, not a new version."""
    return existing == incoming

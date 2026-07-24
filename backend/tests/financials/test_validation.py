from decimal import Decimal

import pytest

from nivesh.financials.validation import (
    InvalidFinancialDataError,
    is_duplicate_statement,
    validate_accounting_equation,
    validate_balance_sheet_fields,
    validate_cash_flow_fields,
    validate_currency,
    validate_profit_and_loss_fields,
    validate_reporting_period,
)


def test_valid_annual_reporting_period_passes():
    validate_reporting_period(
        period_type="annual", fiscal_year=2025, fiscal_period="FY", period_end_date_year=2025
    )  # should not raise


def test_valid_quarterly_reporting_period_passes():
    validate_reporting_period(
        period_type="quarterly", fiscal_year=2025, fiscal_period="Q3", period_end_date_year=2025
    )  # should not raise


def test_unknown_period_type_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_reporting_period(
            period_type="monthly", fiscal_year=2025, fiscal_period="FY", period_end_date_year=2025
        )


def test_annual_statement_with_non_fy_fiscal_period_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_reporting_period(
            period_type="annual", fiscal_year=2025, fiscal_period="Q1", period_end_date_year=2025
        )


def test_quarterly_statement_with_invalid_fiscal_period_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_reporting_period(
            period_type="quarterly",
            fiscal_year=2025,
            fiscal_period="FY",
            period_end_date_year=2025,
        )


def test_implausibly_old_fiscal_year_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_reporting_period(
            period_type="annual", fiscal_year=1800, fiscal_period="FY", period_end_date_year=1800
        )


def test_fiscal_year_far_from_period_end_year_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_reporting_period(
            period_type="annual", fiscal_year=2020, fiscal_period="FY", period_end_date_year=2025
        )


def test_fiscal_year_one_year_off_period_end_year_is_allowed():
    validate_reporting_period(
        period_type="annual", fiscal_year=2024, fiscal_period="FY", period_end_date_year=2025
    )  # should not raise


def test_valid_currency_passes():
    validate_currency("INR")  # should not raise


def test_currency_with_wrong_length_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_currency("RUPEE")


def test_empty_currency_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_currency("")


def test_currency_inconsistent_with_expected_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_currency("USD", expected_currency="INR")


def test_currency_matching_expected_case_insensitively_passes():
    validate_currency("inr", expected_currency="INR")  # should not raise


def test_balance_sheet_missing_total_assets_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_balance_sheet_fields(
            {"total_assets": None, "total_liabilities": Decimal("10"), "total_equity": Decimal("5")}
        )


def test_balance_sheet_with_all_required_fields_passes():
    validate_balance_sheet_fields(
        {
            "total_assets": Decimal("100"),
            "total_liabilities": Decimal("60"),
            "total_equity": Decimal("40"),
        }
    )  # should not raise


def test_profit_and_loss_missing_net_income_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_profit_and_loss_fields({"total_revenue": Decimal("100"), "net_income": None})


def test_cash_flow_missing_operating_cash_flow_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_cash_flow_fields({"operating_cash_flow": None})


def test_accounting_equation_balances_within_tolerance():
    validate_accounting_equation(Decimal("100"), Decimal("60"), Decimal("40"))  # should not raise


def test_accounting_equation_small_rounding_difference_is_tolerated():
    validate_accounting_equation(Decimal("100"), Decimal("60"), Decimal("41"))  # 1% off, within 2%


def test_accounting_equation_large_mismatch_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_accounting_equation(Decimal("100"), Decimal("50"), Decimal("10"))


def test_accounting_equation_skips_when_a_figure_is_missing():
    validate_accounting_equation(None, Decimal("60"), Decimal("40"))  # should not raise


def test_accounting_equation_zero_assets_with_nonzero_other_side_is_rejected():
    with pytest.raises(InvalidFinancialDataError):
        validate_accounting_equation(Decimal("0"), Decimal("10"), Decimal("0"))


def test_accounting_equation_all_zero_passes():
    validate_accounting_equation(Decimal("0"), Decimal("0"), Decimal("0"))  # should not raise


def test_is_duplicate_statement_true_for_identical_signatures():
    signature = {"total_assets": Decimal("100"), "net_income": Decimal("10")}
    assert is_duplicate_statement(signature, dict(signature)) is True


def test_is_duplicate_statement_false_when_a_value_changed():
    existing = {"total_assets": Decimal("100"), "net_income": Decimal("10")}
    incoming = {"total_assets": Decimal("105"), "net_income": Decimal("10")}
    assert is_duplicate_statement(existing, incoming) is False

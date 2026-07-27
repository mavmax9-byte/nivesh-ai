from datetime import date

import pytest

from nivesh.corporate_filings.models import FILING_TYPE_ANNUAL_REPORT, FILING_TYPE_QUARTERLY_RESULTS
from nivesh.corporate_filings.validation import (
    InvalidFilingDataError,
    is_duplicate_filing,
    validate_checksum_format,
    validate_filing_type,
    validate_reporting_period,
    validate_required_fields,
    validate_source_url,
    validate_version_sequence,
)

_VALID_CHECKSUM = "a" * 64


def _filing_data(**overrides) -> dict:
    defaults = dict(
        exchange="NSE",
        filing_type=FILING_TYPE_QUARTERLY_RESULTS,
        title="TCS Quarterly Results - Q2FY2026",
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
        source_url="https://www.nseindia.com/get-quotes/equity?symbol=TCS",
        checksum=_VALID_CHECKSUM,
        language="en",
    )
    defaults.update(overrides)
    return defaults


def test_valid_filing_type_passes():
    validate_filing_type(FILING_TYPE_ANNUAL_REPORT)  # should not raise


def test_unknown_filing_type_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_filing_type("press_release")


def test_valid_https_url_passes():
    validate_source_url("https://www.nseindia.com/get-quotes/equity?symbol=TCS")  # should not raise


def test_url_without_scheme_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_source_url("www.nseindia.com/tcs")


def test_url_with_unsupported_scheme_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_source_url("ftp://nseindia.com/tcs")


def test_url_without_host_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_source_url("https://")


def test_valid_checksum_passes():
    validate_checksum_format(_VALID_CHECKSUM)  # should not raise


def test_short_checksum_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_checksum_format("abc123")


def test_non_hex_checksum_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_checksum_format("z" * 64)


def test_quarterly_reporting_period_passes():
    validate_reporting_period(
        filing_type=FILING_TYPE_QUARTERLY_RESULTS,
        reporting_period="Q2FY2026",
        filing_date=date(2026, 10, 15),
    )  # should not raise


def test_annual_reporting_period_passes():
    validate_reporting_period(
        filing_type=FILING_TYPE_ANNUAL_REPORT,
        reporting_period="FY2026",
        filing_date=date(2026, 3, 31),
    )  # should not raise


def test_quarterly_reporting_period_rejects_annual_format():
    with pytest.raises(InvalidFilingDataError):
        validate_reporting_period(
            filing_type=FILING_TYPE_QUARTERLY_RESULTS,
            reporting_period="FY2026",
            filing_date=date(2026, 10, 15),
        )


def test_annual_reporting_period_rejects_quarterly_format():
    with pytest.raises(InvalidFilingDataError):
        validate_reporting_period(
            filing_type=FILING_TYPE_ANNUAL_REPORT,
            reporting_period="Q2FY2026",
            filing_date=date(2026, 3, 31),
        )


def test_reporting_period_year_far_from_filing_date_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_reporting_period(
            filing_type=FILING_TYPE_ANNUAL_REPORT,
            reporting_period="FY2020",
            filing_date=date(2026, 3, 31),
        )


def test_reporting_period_year_one_off_filing_date_is_allowed():
    validate_reporting_period(
        filing_type=FILING_TYPE_ANNUAL_REPORT,
        reporting_period="FY2025",
        filing_date=date(2026, 3, 31),
    )  # should not raise


def test_required_fields_all_present_passes():
    validate_required_fields(_filing_data())  # should not raise


def test_required_fields_missing_title_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_required_fields(_filing_data(title=""))


def test_required_fields_missing_checksum_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_required_fields(_filing_data(checksum=None))


def test_version_sequence_first_version_passes():
    validate_version_sequence(None, 1)  # should not raise


def test_version_sequence_next_version_passes():
    validate_version_sequence(2, 3)  # should not raise


def test_version_sequence_gap_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_version_sequence(1, 3)


def test_version_sequence_non_incrementing_is_rejected():
    with pytest.raises(InvalidFilingDataError):
        validate_version_sequence(2, 2)


def test_is_duplicate_filing_true_for_matching_checksums():
    assert is_duplicate_filing(_VALID_CHECKSUM, _VALID_CHECKSUM) is True


def test_is_duplicate_filing_false_for_different_checksums():
    assert is_duplicate_filing(_VALID_CHECKSUM, "b" * 64) is False

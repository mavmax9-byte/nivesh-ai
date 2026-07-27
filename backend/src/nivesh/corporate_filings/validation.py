"""Pure validation rules for provider-sourced corporate filings metadata.

No I/O, no side effects -- kept separate from CorporateFilingsService so
the rules are independently testable and reusable regardless of which
provider or which service method needs them, mirroring
market_data/validation.py and financials/validation.py's separation.

Checksum *uniqueness* (a different filing identity must never reuse
another filing's checksum) needs a database lookup and so is enforced by
the service and by the `uq_corporate_filings_checksum` constraint, not
here -- this module only validates the checksum's own format.
"""

import re
from datetime import date
from urllib.parse import urlparse

from fastapi import status

from nivesh.core.exceptions import NiveshError
from nivesh.corporate_filings.models import QUARTERLY_FILING_TYPES, VALID_FILING_TYPES

REQUIRED_FILING_FIELDS = (
    "exchange",
    "filing_type",
    "title",
    "reporting_period",
    "filing_date",
    "source_url",
    "checksum",
    "language",
)

_ANNUAL_PERIOD_PATTERN = re.compile(r"^FY\d{4}$")
_QUARTERLY_PERIOD_PATTERN = re.compile(r"^Q[1-4]FY\d{4}$")
# Hex digest, e.g. a SHA-256 checksum (64 hex chars) -- the length a
# provider's checksum must be at least as long as to be a meaningful
# content fingerprint rather than a placeholder string.
_CHECKSUM_PATTERN = re.compile(r"^[0-9a-fA-F]{32,}$")
_MAX_REPORTING_PERIOD_YEAR_DRIFT = 1


class InvalidFilingDataError(NiveshError):
    """Raised when provider-sourced filing data fails a validation rule
    that should halt persistence of that filing."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_FILING_DATA"


def validate_required_fields(data: dict) -> None:
    for field in REQUIRED_FILING_FIELDS:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise InvalidFilingDataError(f"Filing is missing required field '{field}'.")


def validate_filing_type(filing_type: str) -> None:
    if filing_type not in VALID_FILING_TYPES:
        raise InvalidFilingDataError(f"Unknown filing_type '{filing_type}'.")


def validate_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidFilingDataError(f"'{source_url}' is not a valid http(s) URL.")


def validate_checksum_format(checksum: str) -> None:
    if not _CHECKSUM_PATTERN.match(checksum):
        raise InvalidFilingDataError(
            f"'{checksum}' is not a valid checksum "
            "(expected a hex digest of at least 32 characters)."
        )


def validate_reporting_period(
    *, filing_type: str, reporting_period: str, filing_date: date
) -> None:
    pattern = (
        _QUARTERLY_PERIOD_PATTERN
        if filing_type in QUARTERLY_FILING_TYPES
        else _ANNUAL_PERIOD_PATTERN
    )
    if not pattern.match(reporting_period):
        raise InvalidFilingDataError(
            f"reporting_period '{reporting_period}' is not valid for filing_type '{filing_type}'."
        )

    period_year = int(reporting_period[-4:])
    if abs(period_year - filing_date.year) > _MAX_REPORTING_PERIOD_YEAR_DRIFT:
        raise InvalidFilingDataError(
            f"reporting_period '{reporting_period}' is inconsistent with filing_date {filing_date}."
        )


def validate_version_sequence(existing_version: int | None, incoming_version: int) -> None:
    expected = (existing_version or 0) + 1
    if incoming_version != expected:
        raise InvalidFilingDataError(
            f"version_number {incoming_version} is not the next version after "
            f"{existing_version} (expected {expected})."
        )


def is_duplicate_filing(existing_checksum: str, incoming_checksum: str) -> bool:
    """True when incoming filing metadata is identical to what is already
    stored for this filing identity -- re-syncing unchanged provider data
    should be a no-op, not a new version."""
    return existing_checksum == incoming_checksum

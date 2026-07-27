"""Normalization of provider DTOs into repository-ready persistence payloads.

Pure functions -- no I/O, no side effects. Category and source lookups
require a database round trip (`get_or_create_by_code`), so they are
resolved by the service before calling into this module; these functions
only ever combine already-resolved ids with already-fetched provider data.
"""

import uuid

from nivesh.corporate_filings.models import (
    CATEGORY_CORPORATE_ACTIONS,
    CATEGORY_DISCLOSURES,
    CATEGORY_FINANCIAL_RESULTS,
    CATEGORY_GOVERNANCE,
    CATEGORY_INVESTOR_COMMUNICATION,
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_BOARD_MEETING,
    FILING_TYPE_CORPORATE_ACTION,
    FILING_TYPE_CREDIT_RATING,
    FILING_TYPE_INVESTOR_PRESENTATION,
    FILING_TYPE_OTHER,
    FILING_TYPE_QUARTERLY_RESULTS,
    FILING_TYPE_REGULATORY_DISCLOSURE,
    FILING_TYPE_SHAREHOLDING_PATTERN,
)
from nivesh.corporate_filings.providers.base import ProviderFiling

# Deterministic filing_type -> (category code, category display name)
# mapping -- the only "classification" this sprint performs; no AI, no
# inference, just a fixed lookup table.
FILING_TYPE_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    FILING_TYPE_ANNUAL_REPORT: (CATEGORY_FINANCIAL_RESULTS, "Financial Results"),
    FILING_TYPE_QUARTERLY_RESULTS: (CATEGORY_FINANCIAL_RESULTS, "Financial Results"),
    FILING_TYPE_BOARD_MEETING: (CATEGORY_GOVERNANCE, "Governance"),
    FILING_TYPE_SHAREHOLDING_PATTERN: (CATEGORY_GOVERNANCE, "Governance"),
    FILING_TYPE_CORPORATE_ACTION: (CATEGORY_CORPORATE_ACTIONS, "Corporate Actions"),
    FILING_TYPE_INVESTOR_PRESENTATION: (
        CATEGORY_INVESTOR_COMMUNICATION,
        "Investor Communication",
    ),
    FILING_TYPE_CREDIT_RATING: (CATEGORY_DISCLOSURES, "Disclosures"),
    FILING_TYPE_REGULATORY_DISCLOSURE: (CATEGORY_DISCLOSURES, "Disclosures"),
    FILING_TYPE_OTHER: (CATEGORY_DISCLOSURES, "Disclosures"),
}


def category_for_filing_type(filing_type: str) -> tuple[str, str]:
    """Returns (category_code, category_name) for a filing_type.

    Callers are expected to have already validated filing_type against
    VALID_FILING_TYPES, so every key is guaranteed present here.
    """
    return FILING_TYPE_CATEGORY_MAP[filing_type]


def normalize_filing(
    *,
    company_id: uuid.UUID,
    category_id: uuid.UUID,
    source_id: uuid.UUID,
    filing: ProviderFiling,
) -> dict:
    return {
        "company_id": company_id,
        "category_id": category_id,
        "source_id": source_id,
        "exchange": filing.exchange,
        "filing_type": filing.filing_type,
        "title": filing.title,
        "reporting_period": filing.reporting_period,
        "filing_date": filing.filing_date,
        "source_url": filing.source_url,
        "checksum": filing.checksum,
        "language": filing.language,
        "document_size": filing.document_size,
    }


def normalize_filing_version(
    *, filing_id: uuid.UUID, company_id: uuid.UUID, version_number: int, filing_data: dict
) -> dict:
    """Builds a FilingVersion snapshot from a normalized filing dict (see
    `normalize_filing`) plus the version_number the service has computed."""
    return {
        "filing_id": filing_id,
        "company_id": company_id,
        "version_number": version_number,
        "title": filing_data["title"],
        "filing_date": filing_data["filing_date"],
        "source_url": filing_data["source_url"],
        "checksum": filing_data["checksum"],
        "document_size": filing_data["document_size"],
    }

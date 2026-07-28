"""Pure validation rules for provider-sourced document extractions.

No I/O, no side effects -- kept separate from DocumentIntelligenceService so
the rules are independently testable and reusable regardless of which
provider or which service method needs them, mirroring market_data/
financials/corporate_filings' validation.py separation. Every rule here
raises before anything is persisted, the same "validate first, write once"
convention used throughout this codebase -- there is no "failed" row left
behind by a rejected extraction.
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError
from nivesh.corporate_filings.models import (
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_INVESTOR_PRESENTATION,
    FILING_TYPE_QUARTERLY_RESULTS,
)
from nivesh.document_intelligence.models import DocumentExtraction
from nivesh.document_intelligence.normalization import NormalizedExtraction, NormalizedSection
from nivesh.document_intelligence.providers.base import ProviderExtractionResult

# filing_type values this sprint knows how to extract -- Annual Reports,
# Quarterly Reports, and Investor Presentations, per the sprint scope. Other
# filing types (board meetings, shareholding patterns, corporate actions,
# credit ratings, regulatory disclosures) are metadata-only in Corporate
# Filings and are not document-bearing in the way this sprint models.
EXTRACTABLE_FILING_TYPES = {
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_QUARTERLY_RESULTS,
    FILING_TYPE_INVESTOR_PRESENTATION,
}

# Below this ratio of alphanumeric-or-whitespace characters, extracted text
# is treated as corrupted (garbled encoding, control characters from a
# malformed/encrypted PDF) rather than a legitimate low-density document.
_MIN_CLEAN_CHARACTER_RATIO = 0.6


class InvalidDocumentExtractionError(NiveshError):
    """Raised when an extraction result fails a validation rule that should
    halt persistence of that extraction."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "INVALID_DOCUMENT_EXTRACTION"


class DuplicateExtractionError(NiveshError):
    """Raised when a filing version already has an extraction -- re-running
    extraction for the same identity is a conflict, not a new version (see
    models.py: a filing version has at most one extraction)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_EXTRACTION"


def validate_extractable_filing_type(filing_type: str) -> None:
    if filing_type not in EXTRACTABLE_FILING_TYPES:
        raise InvalidDocumentExtractionError(
            f"filing_type '{filing_type}' is not extractable "
            f"(expected one of {sorted(EXTRACTABLE_FILING_TYPES)})."
        )


def validate_no_duplicate_extraction(existing: DocumentExtraction | None) -> None:
    if existing is not None:
        raise DuplicateExtractionError(
            f"filing version '{existing.filing_version_id}' has already been extracted."
        )


def validate_non_empty_document(normalized: NormalizedExtraction) -> None:
    if normalized.page_count == 0:
        raise InvalidDocumentExtractionError("Document has no pages to extract.")
    if not normalized.extracted_text.strip():
        raise InvalidDocumentExtractionError(
            "Document produced no extractable text (empty or image-only document)."
        )


def validate_not_corrupted(normalized: NormalizedExtraction) -> None:
    """Rejects extractions whose text is mostly non-printable/control noise
    -- a mechanical signal of a malformed, encrypted, or unsupported PDF,
    not an interpretation of the document's content."""
    text = normalized.extracted_text
    if not text:
        return

    clean_chars = sum(1 for char in text if char.isalnum() or char.isspace())
    clean_ratio = clean_chars / len(text)
    if clean_ratio < _MIN_CLEAN_CHARACTER_RATIO:
        raise InvalidDocumentExtractionError(
            f"Extracted text appears corrupted (clean-character ratio "
            f"{clean_ratio:.2f} below minimum {_MIN_CLEAN_CHARACTER_RATIO})."
        )


def validate_page_consistency(result: ProviderExtractionResult) -> None:
    """Page numbers must be the contiguous sequence 1..N, in order --
    anything else means the provider's pagination cannot be trusted."""
    expected = list(range(1, len(result.pages) + 1))
    actual = [page.page_number for page in result.pages]
    if actual != expected:
        raise InvalidDocumentExtractionError(
            f"Page numbers are not a contiguous 1..N sequence: got {actual}."
        )


def validate_section_consistency(sections: list[NormalizedSection]) -> None:
    """Sections must be in strictly increasing sequence order, and each
    section's page number must not precede the previous section's -- a
    section hierarchy that jumps backward in the document is inconsistent."""
    previous_sequence = -1
    previous_page = -1
    for section in sections:
        if section.sequence != previous_sequence + 1:
            raise InvalidDocumentExtractionError(
                f"Section sequence is not contiguous: expected "
                f"{previous_sequence + 1}, got {section.sequence}."
            )
        if section.page_number < previous_page:
            raise InvalidDocumentExtractionError(
                f"Section '{section.heading}' (page {section.page_number}) precedes "
                f"an earlier section on page {previous_page}."
            )
        previous_sequence = section.sequence
        previous_page = section.page_number

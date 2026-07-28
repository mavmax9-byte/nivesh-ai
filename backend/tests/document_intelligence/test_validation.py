from uuid import uuid4

import pytest

from nivesh.corporate_filings.models import (
    FILING_TYPE_ANNUAL_REPORT,
    FILING_TYPE_BOARD_MEETING,
    FILING_TYPE_QUARTERLY_RESULTS,
)
from nivesh.document_intelligence.models import EXTRACTION_STATUS_COMPLETED, DocumentExtraction
from nivesh.document_intelligence.normalization import NormalizedExtraction, NormalizedSection
from nivesh.document_intelligence.providers.base import (
    ProviderExtractedPage,
    ProviderExtractionResult,
)
from nivesh.document_intelligence.validation import (
    DuplicateExtractionError,
    InvalidDocumentExtractionError,
    validate_extractable_filing_type,
    validate_no_duplicate_extraction,
    validate_non_empty_document,
    validate_not_corrupted,
    validate_page_consistency,
    validate_section_consistency,
)


def _normalized(text: str = "Some clean text.", page_count: int = 1, sections=None):
    sections = sections or []
    return NormalizedExtraction(
        extracted_text=text,
        page_count=page_count,
        section_count=len(sections),
        sections=sections,
    )


def _section(sequence: int, page_number: int, heading: str = "Heading") -> NormalizedSection:
    return NormalizedSection(
        sequence=sequence, heading=heading, level=1, page_number=page_number, content="Body."
    )


def test_extractable_filing_types_pass():
    validate_extractable_filing_type(FILING_TYPE_ANNUAL_REPORT)  # should not raise
    validate_extractable_filing_type(FILING_TYPE_QUARTERLY_RESULTS)  # should not raise


def test_non_extractable_filing_type_is_rejected():
    with pytest.raises(InvalidDocumentExtractionError):
        validate_extractable_filing_type(FILING_TYPE_BOARD_MEETING)


def test_no_existing_extraction_passes():
    validate_no_duplicate_extraction(None)  # should not raise


def test_existing_extraction_is_rejected_as_duplicate():
    existing = DocumentExtraction(
        id=uuid4(),
        filing_version_id=uuid4(),
        company_id=uuid4(),
        extraction_status=EXTRACTION_STATUS_COMPLETED,
        extractor_name="pypdf",
        extractor_version="5.0.0",
        extracted_text="text",
        page_count=1,
        section_count=1,
    )
    with pytest.raises(DuplicateExtractionError):
        validate_no_duplicate_extraction(existing)


def test_document_with_pages_and_text_passes():
    validate_non_empty_document(_normalized())  # should not raise


def test_document_with_zero_pages_is_rejected():
    with pytest.raises(InvalidDocumentExtractionError):
        validate_non_empty_document(_normalized(page_count=0))


def test_document_with_blank_text_is_rejected():
    with pytest.raises(InvalidDocumentExtractionError):
        validate_non_empty_document(_normalized(text="   \n\n  "))


def test_clean_text_passes_corruption_check():
    validate_not_corrupted(
        _normalized(text="This is perfectly ordinary readable text.")
    )  # should not raise


def test_mostly_control_character_text_is_rejected_as_corrupted():
    garbled = "\x00\x01\x02\x03" * 20 + "ok"
    with pytest.raises(InvalidDocumentExtractionError):
        validate_not_corrupted(_normalized(text=garbled))


def test_contiguous_page_numbers_pass():
    result = ProviderExtractionResult(
        extractor_name="pypdf",
        extractor_version="5.0.0",
        pages=[
            ProviderExtractedPage(page_number=1, text="a"),
            ProviderExtractedPage(page_number=2, text="b"),
        ],
    )
    validate_page_consistency(result)  # should not raise


def test_non_contiguous_page_numbers_are_rejected():
    result = ProviderExtractionResult(
        extractor_name="pypdf",
        extractor_version="5.0.0",
        pages=[
            ProviderExtractedPage(page_number=1, text="a"),
            ProviderExtractedPage(page_number=3, text="b"),
        ],
    )
    with pytest.raises(InvalidDocumentExtractionError):
        validate_page_consistency(result)


def test_contiguous_sections_in_page_order_pass():
    sections = [_section(0, 1), _section(1, 1), _section(2, 2)]
    validate_section_consistency(sections)  # should not raise


def test_non_contiguous_section_sequence_is_rejected():
    sections = [_section(0, 1), _section(2, 1)]
    with pytest.raises(InvalidDocumentExtractionError):
        validate_section_consistency(sections)


def test_section_page_number_going_backward_is_rejected():
    sections = [_section(0, 2), _section(1, 1)]
    with pytest.raises(InvalidDocumentExtractionError):
        validate_section_consistency(sections)

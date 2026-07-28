"""Tests for deterministic heading/section detection and canonical text
construction. Pure functions -- no mocks, no I/O."""

from nivesh.document_intelligence.normalization import normalize_extraction
from nivesh.document_intelligence.providers.base import (
    ProviderExtractedPage,
    ProviderExtractionResult,
)


def _result(pages: list[str]) -> ProviderExtractionResult:
    return ProviderExtractionResult(
        extractor_name="pypdf",
        extractor_version="5.0.0",
        pages=[
            ProviderExtractedPage(page_number=index + 1, text=text)
            for index, text in enumerate(pages)
        ],
    )


def test_page_count_matches_number_of_pages():
    normalized = normalize_extraction(_result(["Some text.", "More text."]))
    assert normalized.page_count == 2


def test_canonical_text_includes_page_markers():
    normalized = normalize_extraction(_result(["First page body."]))
    assert "--- Page 1 ---" in normalized.extracted_text
    assert "First page body." in normalized.extracted_text


def test_numbered_heading_is_detected_with_correct_level():
    text = "1. Overview\nSome introductory text.\n1.1 Background\nMore detail here."
    normalized = normalize_extraction(_result([text]))

    headings = [(section.heading, section.level) for section in normalized.sections]
    assert ("1. Overview", 1) in headings
    assert ("1.1 Background", 2) in headings


def test_all_caps_heading_is_detected_as_level_one():
    text = "FINANCIAL HIGHLIGHTS\nRevenue grew twenty percent year over year."
    normalized = normalize_extraction(_result([text]))

    assert normalized.sections[0].heading == "FINANCIAL HIGHLIGHTS"
    assert normalized.sections[0].level == 1


def test_title_case_short_heading_is_detected_as_level_two():
    text = "Management Discussion\nThe company performed well this quarter."
    normalized = normalize_extraction(_result([text]))

    assert normalized.sections[0].heading == "Management Discussion"
    assert normalized.sections[0].level == 2


def test_long_sentence_is_not_treated_as_heading():
    text = (
        "This is a long descriptive sentence that goes on for quite a while "
        "and should never be mistaken for a heading, since it ends with a period."
    )
    normalized = normalize_extraction(_result([text]))

    assert len(normalized.sections) == 1
    assert normalized.sections[0].heading == "Document"


def test_preamble_before_first_heading_is_captured():
    text = "Some intro line.\nANNUAL REPORT\nBody content follows."
    normalized = normalize_extraction(_result([text]))

    assert normalized.sections[0].heading == "Document"
    assert normalized.sections[0].content == "Some intro line."
    assert normalized.sections[1].heading == "ANNUAL REPORT"
    assert normalized.sections[1].content == "Body content follows."


def test_section_page_numbers_track_the_page_the_heading_appeared_on():
    normalized = normalize_extraction(
        _result(["FIRST SECTION\nContent on page one.", "SECOND SECTION\nContent on page two."])
    )

    pages = {section.heading: section.page_number for section in normalized.sections}
    assert pages["FIRST SECTION"] == 1
    assert pages["SECOND SECTION"] == 2


def test_empty_document_has_no_sections():
    normalized = normalize_extraction(_result([]))

    assert normalized.page_count == 0
    assert normalized.section_count == 0
    assert normalized.sections == []
    assert normalized.extracted_text == ""


def test_section_count_matches_number_of_sections():
    normalized = normalize_extraction(_result(["ONE\nfirst.\nTWO\nsecond.\nTHREE\nthird."]))
    assert normalized.section_count == len(normalized.sections) == 3


def test_section_sequence_is_contiguous_from_zero():
    normalized = normalize_extraction(_result(["ONE\nfirst.\nTWO\nsecond.\nTHREE\nthird."]))
    assert [section.sequence for section in normalized.sections] == list(
        range(len(normalized.sections))
    )

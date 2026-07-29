from nivesh.knowledge_layer.normalization import (
    build_company_profile_text,
    build_corporate_filing_text,
    build_document_section_text,
    build_news_article_text,
    build_research_summary_text,
    compute_content_checksum,
    truncate_for_embedding,
)


def test_build_company_profile_text_includes_all_available_fields():
    text = build_company_profile_text(
        symbol="TCS", name="Tata Consultancy Services", sector="Technology", industry="IT Services"
    )
    assert "Tata Consultancy Services" in text
    assert "Symbol: TCS" in text
    assert "Sector: Technology" in text
    assert "Industry: IT Services" in text


def test_build_company_profile_text_omits_missing_optional_fields():
    text = build_company_profile_text(
        symbol="TCS", name="Tata Consultancy Services", sector=None, industry=None
    )
    assert "Sector" not in text
    assert "Industry" not in text


def test_build_corporate_filing_text_includes_identity_fields():
    text = build_corporate_filing_text(
        title="Q1 FY26 Results",
        filing_type="quarterly_results",
        reporting_period="Q1FY26",
        category_name="Financial Results",
    )
    assert "Q1 FY26 Results" in text
    assert "Financial Results" in text
    assert "quarterly_results" in text
    assert "Q1FY26" in text


def test_build_document_section_text_combines_heading_and_content():
    text = build_document_section_text(heading="Risk Factors", content="Market risk is...")
    assert text.startswith("Risk Factors")
    assert "Market risk is..." in text


def test_build_news_article_text_combines_title_and_summary():
    text = build_news_article_text(title="TCS beats estimates", summary="Revenue rose 5%.")
    assert text == "TCS beats estimates. Revenue rose 5%."


def test_build_news_article_text_handles_empty_summary():
    text = build_news_article_text(title="TCS beats estimates", summary="")
    assert text == "TCS beats estimates"


def test_build_research_summary_text_returns_change_summary_verbatim():
    assert build_research_summary_text(change_summary="Price and filings updated.") == (
        "Price and filings updated."
    )


def test_truncate_for_embedding_strips_and_bounds_length():
    long_text = "a" * 9000
    result = truncate_for_embedding(f"  {long_text}  ")
    assert len(result) == 8000
    assert result == long_text[:8000]


def test_compute_content_checksum_is_deterministic():
    assert compute_content_checksum("hello") == compute_content_checksum("hello")


def test_compute_content_checksum_differs_for_different_text():
    assert compute_content_checksum("hello") != compute_content_checksum("world")

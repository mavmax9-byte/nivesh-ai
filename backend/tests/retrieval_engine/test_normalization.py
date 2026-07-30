from datetime import date, timedelta
from uuid import uuid4

import pytest

from nivesh.retrieval_engine.normalization import (
    RECENCY_HALF_LIFE_DAYS,
    ContextPackage,
    EvidenceItem,
    build_context_package,
    build_context_text,
    clamp_score,
    deduplicate_and_rank,
    recency_score,
    semantic_score,
    truncate_query,
    truncate_snippet,
)


def _item(source_type="news_article", source_id=None, score=0.5, via=("structured",), **overrides):
    defaults = dict(
        source_type=source_type,
        source_table="news_articles",
        source_id=source_id or uuid4(),
        title="Title",
        snippet="Snippet",
        evidence_date=date(2026, 7, 1),
        relevance_score=score,
        retrieved_via=via,
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


def test_clamp_score_bounds_to_zero_one():
    assert clamp_score(-0.5) == 0.0
    assert clamp_score(1.5) == 1.0
    assert clamp_score(0.42) == pytest.approx(0.42)


def test_recency_score_is_one_for_todays_evidence():
    today = date(2026, 7, 30)
    assert recency_score(today, today) == pytest.approx(1.0)


def test_recency_score_decays_to_half_at_half_life():
    today = date(2026, 7, 30)
    aged = today - timedelta(days=RECENCY_HALF_LIFE_DAYS)
    assert recency_score(aged, today) == pytest.approx(0.5, abs=1e-6)


def test_recency_score_never_negative_for_future_dates():
    today = date(2026, 7, 30)
    future = date(2026, 8, 15)
    assert recency_score(future, today) == pytest.approx(1.0)


def test_recency_score_returns_default_for_missing_date():
    assert recency_score(None, date(2026, 7, 30)) == 0.1


def test_semantic_score_converts_distance_to_similarity():
    assert semantic_score(0.0) == pytest.approx(1.0)
    assert semantic_score(1.0) == pytest.approx(0.0)
    assert semantic_score(2.0) == pytest.approx(0.0)  # clamped, cosine distance can reach 2


def test_deduplicate_and_rank_orders_by_score_descending():
    items = [_item(score=0.2), _item(score=0.9), _item(score=0.5)]
    ranked = deduplicate_and_rank(items, limit=10)
    assert [item.relevance_score for item in ranked] == [0.9, 0.5, 0.2]


def test_deduplicate_and_rank_merges_same_source_keeping_higher_score():
    shared_id = uuid4()
    semantic_hit = _item(source_id=shared_id, score=0.4, via=("semantic",))
    structured_hit = _item(source_id=shared_id, score=0.8, via=("structured",))

    ranked = deduplicate_and_rank([semantic_hit, structured_hit], limit=10)

    assert len(ranked) == 1
    assert ranked[0].relevance_score == pytest.approx(0.8)
    assert set(ranked[0].retrieved_via) == {"semantic", "structured"}


def test_deduplicate_and_rank_respects_limit():
    items = [_item(score=score) for score in (0.1, 0.2, 0.3, 0.4, 0.5)]
    ranked = deduplicate_and_rank(items, limit=2)
    assert len(ranked) == 2
    assert ranked[0].relevance_score == pytest.approx(0.5)
    assert ranked[1].relevance_score == pytest.approx(0.4)


def test_deduplicate_and_rank_keeps_distinct_items_by_type_and_id():
    item_a = _item(source_type="news_article", source_id=uuid4())
    item_b = _item(source_type="corporate_filing", source_id=item_a.source_id)
    ranked = deduplicate_and_rank([item_a, item_b], limit=10)
    assert len(ranked) == 2


def test_build_context_text_includes_citation_metadata_and_snippet():
    item = _item(title="TCS beats estimates", snippet="Revenue rose.", score=0.75)
    text = build_context_text("TCS", "revenue growth", [item])
    assert "TCS" in text
    assert "revenue growth" in text
    assert "TCS beats estimates" in text
    assert "Revenue rose." in text
    assert "0.750" in text
    assert item.evidence_date.isoformat() in text


def test_build_context_text_handles_undated_evidence():
    item = _item(evidence_date=None)
    text = build_context_text("TCS", "q", [item])
    assert "undated" in text


def test_build_context_package_wraps_evidence_and_generates_text():
    item = _item()
    package = build_context_package("TCS", "revenue", [item])
    assert isinstance(package, ContextPackage)
    assert package.symbol == "TCS"
    assert package.evidence == (item,)
    assert "TCS" in package.context_text


def test_truncate_query_strips_and_bounds_length():
    result = truncate_query("  " + ("a" * 3000) + "  ")
    assert len(result) == 2000


def test_truncate_snippet_strips_and_bounds_length():
    result = truncate_snippet("  " + ("b" * 1000) + "  ")
    assert len(result) == 500

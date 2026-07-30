"""Evidence scoring, deduplication/ranking, and context-package assembly.

Pure functions and frozen dataclasses -- no I/O, no side effects, mirroring
every other module's normalization.py separation.

**Scoring is deterministic, not learned or LLM-based** -- consistent with
this codebase's house style (see e.g. news_intelligence's keyword
categorizer, document_intelligence's heading heuristics). Two different
scoring functions feed one common 0..1 `relevance_score` scale:

- Semantic hits (from the Knowledge Layer) are scored by cosine
  similarity (`1 - cosine_distance`), which is already approximately
  0..1 for real embeddings; `clamp_score` guards the edges.
- Structured SQL evidence (financial statements, technical indicators,
  corporate filings, document sections, news articles fetched directly,
  not via semantic match) has no query-relevance signal to score against
  -- "structured SQL retrieval" is a filter/fetch, not a similarity
  search. It is scored instead by **recency**: an exponential decay from
  1.0 (today) toward 0.0 as evidence ages, with a single shared half-life
  (`RECENCY_HALF_LIFE_DAYS`) across all structured source types. A single
  shared half-life (rather than a per-type tuned value) is a deliberate
  simplification for this foundational version -- easy to reason about
  and adjust later, not backed by empirical tuning.

An evidence item found via **both** paths (e.g. a news article that is
both the company's most recent story *and* a semantic match for the
query) is deduplicated to one item by `(source_type, source_id)`, keeping
the higher of the two scores and recording both retrieval paths in
`retrieved_via` -- see `deduplicate_and_rank`.
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

# Days for a structured evidence item's recency score to decay to 0.5.
# A single shared value across all structured source types -- see module
# docstring for why this is a deliberate simplification.
RECENCY_HALF_LIFE_DAYS = 180

# Fallback score for the rare item with no usable date at all (should not
# happen for any source type this version fetches, since every one has at
# least an approximate date -- see service.py's per-source evidence
# builders) -- kept only as a defensive floor, not a real code path.
DEFAULT_SCORE_NO_DATE = 0.1

# Defensive character bounds -- a query is a short search phrase in
# practice, and an evidence snippet is for citation display, not a full
# document; both are truncated rather than validated/rejected, the same
# "truncate, don't fail" choice knowledge_layer's own normalization.py
# makes for embedding input.
MAX_QUERY_CHARS = 2000
MAX_SNIPPET_CHARS = 500


def truncate_query(query: str) -> str:
    return query.strip()[:MAX_QUERY_CHARS]


def truncate_snippet(text: str) -> str:
    return text.strip()[:MAX_SNIPPET_CHARS]


@dataclass(frozen=True)
class EvidenceItem:
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str
    snippet: str
    evidence_date: date | None
    relevance_score: float
    retrieved_via: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContextPackage:
    symbol: str
    query: str
    generated_at: datetime
    evidence: tuple[EvidenceItem, ...]
    context_text: str


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def recency_score(evidence_date: date | None, as_of: date) -> float:
    if evidence_date is None:
        return DEFAULT_SCORE_NO_DATE
    age_days = max(0, (as_of - evidence_date).days)
    return clamp_score(math.exp(-math.log(2) * age_days / RECENCY_HALF_LIFE_DAYS))


def semantic_score(cosine_distance: float) -> float:
    return clamp_score(1.0 - cosine_distance)


def deduplicate_and_rank(items: list[EvidenceItem], limit: int) -> list[EvidenceItem]:
    """Merges items sharing `(source_type, source_id)` -- keeping the
    higher relevance_score and the union of retrieval paths -- then
    returns the top `limit` by relevance_score, highest first."""
    merged: dict[tuple[str, uuid.UUID], EvidenceItem] = {}
    for item in items:
        key = (item.source_type, item.source_id)
        existing = merged.get(key)
        if existing is None:
            merged[key] = item
            continue
        via = tuple(sorted(set(existing.retrieved_via) | set(item.retrieved_via)))
        winner = existing if existing.relevance_score >= item.relevance_score else item
        merged[key] = EvidenceItem(
            source_type=winner.source_type,
            source_table=winner.source_table,
            source_id=winner.source_id,
            title=winner.title,
            snippet=winner.snippet,
            evidence_date=winner.evidence_date,
            relevance_score=winner.relevance_score,
            retrieved_via=via,
        )

    ranked = sorted(merged.values(), key=lambda item: item.relevance_score, reverse=True)
    return ranked[:limit]


def build_context_text(symbol: str, query: str, evidence: list[EvidenceItem]) -> str:
    """Deterministic, citation-annotated plain text block -- suitable as
    the evidence section of a downstream LLM prompt. Building this string
    is formatting, not reasoning: every line is copied from already-scored
    evidence, nothing here summarizes or interprets it."""
    lines = [f'Evidence for {symbol} -- query: "{query}"']
    for index, item in enumerate(evidence, start=1):
        date_label = item.evidence_date.isoformat() if item.evidence_date else "undated"
        lines.append(
            f"[{index}] ({item.source_type}, {date_label}, "
            f"relevance={item.relevance_score:.3f}) {item.title}"
        )
        if item.snippet:
            lines.append(f"    {item.snippet}")
    return "\n".join(lines)


def build_context_package(symbol: str, query: str, evidence: list[EvidenceItem]) -> ContextPackage:
    return ContextPackage(
        symbol=symbol,
        query=query,
        generated_at=datetime.now(UTC),
        evidence=tuple(evidence),
        context_text=build_context_text(symbol, query, evidence),
    )

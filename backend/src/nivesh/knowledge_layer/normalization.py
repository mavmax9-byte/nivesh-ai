"""Builds the deterministic text blob embedded for each knowledge source,
and the checksum used to detect whether it changed since the last run.

Pure functions -- no I/O, no side effects. Every `build_*_text` function is
a plain string template over fields already validated and persisted by the
owning module (companies, corporate_filings, document_intelligence,
news_intelligence, research) -- the same "deterministic, not AI" spirit
news_intelligence/normalization.py's `categorize` and
document_intelligence's heading detection already follow, just applied to
building embedding input instead of a classification.

`corporate_filings` has no "sections" of its own (only document_intelligence
does, via DocumentSection) -- `build_corporate_filing_text` embeds the
filing's own descriptive metadata (title, filing type, reporting period) as
one text blob per CorporateFiling row instead. This is a deliberate,
documented interpretation of "corporate filing sections" in the v0.7 spec,
made because the schema has no literal per-filing sections to embed; being
explicit about it here matters for the same reason every provider's own
real-limitations disclosure matters elsewhere in this codebase (see
PROJECT_CONTEXT.md's provider-pattern section).

No chunking in this version: `truncate_for_embedding` bounds a text's
length to a conservative character budget so any single source unit fits
in one embedding call, rather than being split into multiple overlapping
chunks. `_MAX_EMBEDDING_CHARS` is a rough, deliberately conservative proxy
for the ~8191-token input limit `text-embedding-3-small` accepts (roughly
4 characters per token for English text) -- long document sections lose
their tail rather than failing the whole generation run, an accepted,
documented simplification for this foundational version (see
PROJECT_CONTEXT.md's known-limitations section).
"""

import hashlib
import uuid
from dataclasses import dataclass

_MAX_EMBEDDING_CHARS = 8000


@dataclass(frozen=True)
class KnowledgeUnit:
    """One not-yet-embedded piece of textual knowledge, gathered from
    across the platform's existing modules for a single company."""

    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str | None
    content_text: str


def truncate_for_embedding(text: str) -> str:
    return text.strip()[:_MAX_EMBEDDING_CHARS]


def compute_content_checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def build_company_profile_text(
    *, symbol: str, name: str, sector: str | None, industry: str | None
) -> str:
    parts = [name, f"Symbol: {symbol}"]
    if sector:
        parts.append(f"Sector: {sector}")
    if industry:
        parts.append(f"Industry: {industry}")
    return ". ".join(parts)


def build_corporate_filing_text(
    *, title: str, filing_type: str, reporting_period: str, category_name: str
) -> str:
    return f"{title} -- {category_name} ({filing_type}, reporting period {reporting_period})"


def build_document_section_text(*, heading: str, content: str) -> str:
    return f"{heading}\n{content}"


def build_news_article_text(*, title: str, summary: str) -> str:
    return f"{title}. {summary}" if summary else title


def build_research_summary_text(*, change_summary: str) -> str:
    return change_summary

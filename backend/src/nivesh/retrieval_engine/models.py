"""Retrieval Engine module-level constants.

This module owns **no database table** -- a deliberate deviation from
every other module's `models.py` (which always pairs constants with at
least one SQLAlchemy ORM class). `retrieval_engine` doesn't ingest or
persist anything of its own; it only reads evidence other modules already
own and persisted, ranks it, and returns it (see service.py's module
docstring for why this was chosen to be stateless rather than logging
each retrieval run to a new table). There is therefore nothing to model as
a table here -- only the shared vocabulary the rest of the module uses.

`EvidenceSourceType` values name what kind of underlying content an
evidence item represents, independent of *how* it was found (semantic
search vs. structured SQL fetch -- see `EvidenceItem.retrieved_via` in
normalization.py). Five of the seven values are **reused directly** from
`knowledge_layer.models`, not redefined here, because those five source
types can be found via semantic search *and* structured SQL alike (e.g. a
news article can surface either because it matched the query semantically
or because it's simply the company's most recent news) -- reusing the
same string means an item found both ways dedupes correctly by
`(source_type, source_id)`. `financial_statement` and `technical_indicator`
are new here because knowledge_layer explicitly never embeds either (its
own spec excludes "market prices, OHLCV data, technical indicators,
financial statement numeric values") -- they only ever arrive via
structured SQL retrieval.
"""

from nivesh.knowledge_layer.models import (
    SOURCE_TYPE_COMPANY_PROFILE,
    SOURCE_TYPE_CORPORATE_FILING,
    SOURCE_TYPE_DOCUMENT_SECTION,
    SOURCE_TYPE_NEWS_ARTICLE,
    SOURCE_TYPE_RESEARCH_SUMMARY,
    VALID_KNOWLEDGE_SOURCE_TYPES,
)

EVIDENCE_SOURCE_FINANCIAL_STATEMENT = "financial_statement"
EVIDENCE_SOURCE_TECHNICAL_INDICATOR = "technical_indicator"
EVIDENCE_SOURCE_CORPORATE_FILING = SOURCE_TYPE_CORPORATE_FILING
EVIDENCE_SOURCE_DOCUMENT_SECTION = SOURCE_TYPE_DOCUMENT_SECTION
EVIDENCE_SOURCE_NEWS_ARTICLE = SOURCE_TYPE_NEWS_ARTICLE
EVIDENCE_SOURCE_COMPANY_PROFILE = SOURCE_TYPE_COMPANY_PROFILE
EVIDENCE_SOURCE_RESEARCH_SUMMARY = SOURCE_TYPE_RESEARCH_SUMMARY

VALID_EVIDENCE_SOURCE_TYPES = {
    EVIDENCE_SOURCE_FINANCIAL_STATEMENT,
    EVIDENCE_SOURCE_TECHNICAL_INDICATOR,
} | VALID_KNOWLEDGE_SOURCE_TYPES

# How an evidence item was found. An item can be found both ways (a
# structured fetch and a semantic match landing on the same underlying
# row) -- see normalization.py's `deduplicate_and_rank`.
RETRIEVED_VIA_SEMANTIC = "semantic"
RETRIEVED_VIA_STRUCTURED = "structured"

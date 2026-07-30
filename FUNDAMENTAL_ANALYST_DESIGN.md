# Fundamental Analyst — Technical Design Document (v0.9 candidate)

**Status:** DRAFT — for review. No code has been written against this
document. Three architecture forks were raised and settled via explicit
user confirmation during this planning session (see "Decisions Confirmed"
at the end): findings **will** be persisted (a new `agent_findings`
table), numeric cross-checking against stored financials is **deferred**
to a fast-follow, and the LLM vendor/model is **not yet chosen** — the
provider abstraction (§5) is designed to keep that swappable rather than
assuming one. Everything else in this document is still a proposal for
review, following this project's established rhythm (PROJECT_CONTEXT.md
§15 point 3): this report → user confirms scope → implement.

**Author context:** produced during a v0.9 planning session, per the
user's instruction: design the Fundamental Analyst — the first concrete
specialist agent under `ai_agents` — before writing any implementation
code. PROJECT_CONTEXT.md is treated as the source of truth throughout;
every design choice below is checked against it, and every deviation from
existing convention is called out explicitly rather than left implicit.

---

## 0. Framing: what this module is and is not

`ai_agents` is currently 100% placeholder: `BaseAgent`/`AgentContext`/
`AgentFinding` define a contract with no implementation, and
`InvestmentCommitteeOrchestrator.request_analysis` always raises
`NotImplementedYetError` by design — its own docstring says fabricated AI
output would violate the explainability contract before it even exists.
`v0.7` (Knowledge Layer) and `v0.8` (Retrieval Engine) were both explicitly
scoped to stop short of reasoning; `ai_agents` is where reasoning is
finally allowed to begin (PROJECT_CONTEXT.md §13 point 1, §17).

**Fundamental Analyst is the first agent to actually implement `BaseAgent`
and make a real LLM call.** It is scoped narrowly:

- It analyzes one company's **fundamentals** — financial statements,
  ratios, corporate filings, filing-derived document sections, and
  research-dossier summaries — using `retrieval_engine`'s hybrid evidence
  as its only source of facts.
- It produces one structured, cited `AgentFinding` per run. It does not
  call itself, chain into other agents, or talk to the Investment
  Committee orchestrator.
- It never recommends a trade, a buy/sell/hold action, or personalized
  investment advice — consistent with the platform's explicit
  "research/analysis only, never executes trades" identity
  (PROJECT_CONTEXT.md §1). This is treated as a hard compliance
  constraint on the *output*, not just a prompt suggestion (§9 below).

**Explicitly out of scope for this version:**

- Any other specialist agent (Technical, Valuation, News/Sentiment,
  Macro, Risk, Portfolio, Compliance) named in `agents/base.py`'s
  docstring — this document designs a template those can follow later
  (§12), it does not build them.
- `InvestmentCommitteeOrchestrator` implementation — aggregation,
  conflict detection, weighted scoring, LLM synthesis across agents,
  compliance review before publication. It stays a stub.
- A "Findings Store" as a formal cross-agent concept — not yet scoped
  anywhere in this project; this document only ensures Fundamental
  Analyst's output shape doesn't foreclose one being built later.
- Frontend consumption of any of this.
- Changing anything in `retrieval_engine` or `knowledge_layer`. This
  design's working assumption, checked in §3, is **zero changes** to
  either module.

---

## 1. Objectives and Scope

**Objective:** given a company symbol, produce one structured,
evidence-grounded, cited assessment of that company's financial
fundamentals, suitable to hand to a future Investment Committee layer or
to surface directly to a user as "here is what the evidence shows,"
never as "here is what you should do."

**In scope:**

1. A concrete `FundamentalAnalystAgent(BaseAgent)` implementation.
2. An LLM provider abstraction (`ai_agents/providers/`), following the
   exact provider/factory/DTO pattern used by every ingestion module and
   by `knowledge_layer`'s embedding provider (PROJECT_CONTEXT.md §8).
3. A deterministic retrieval → prompt → LLM call → validated JSON →
   `AgentFinding` pipeline, with every non-LLM step (query construction,
   evidence filtering, citation resolution, confidence floor,
   advice-language filtering) implemented as plain Python, not delegated
   to the model.
4. A narrow REST surface to invoke and inspect a run directly (§14),
   since the orchestrator that would otherwise call this agent doesn't
   exist yet.

**Out of scope:** everything listed in §0's "explicitly out of scope"
list, plus: multi-company comparison, historical trend charts, any UI,
and any tuning of retrieval_engine's scoring formula (PROJECT_CONTEXT.md
§12 item 10 — explicitly deferred until an agent is consuming it for
real, which this version would be the first case of; tuning is still a
*separate* future step, not bundled into this one).

---

## 2. Inputs from the Retrieval Engine

Fundamental Analyst consumes exactly one upstream capability:
`RetrievalEngineService.build_context_package(symbol, query, limit)`,
called **in-process** (constructor-injected service, same session-scoped
dependency pattern every other cross-module call in this codebase uses —
never an HTTP self-call to `/retrieval/...`; that endpoint exists for
external/future consumers, not for another backend module to call itself
over the network).

`build_context_package` requires a `query` string (PROJECT_CONTEXT.md
§7's retrieval_engine entry: "`query` is required" because structured
evidence has no text to match against but the semantic leg needs
something to embed). Fundamental Analyst has no free-text user query in
this version — `AgentContext` carries `company_id`/`trigger_type`/
`prior_finding`, nothing resembling a search string — so it supplies a
**fixed, deterministic canonical query constant**, not something derived
per-run:

```
FUNDAMENTAL_ANALYSIS_QUERY = (
    "revenue growth, profitability, margins, balance sheet strength, "
    "debt levels, cash flow, valuation ratios, and overall financial health"
)
```

This is a plain module-level string constant (`ai_agents/agents/
fundamental/queries.py` or similar), the same "deterministic string
template" idiom `knowledge_layer/normalization.py`'s `build_*_text`
functions already establish — not configurable per-request in this
version. A future version could parameterize it (e.g. per-sector
tuning), but that is speculative without real usage data, the same
reasoning PROJECT_CONTEXT.md §12 item 3 already applies to deferring
cross-provider news dedup.

**Evidence-type relevance filter:** `build_context_package` returns
whatever the hybrid retrieval ranks highest across *all* evidence types,
including `technical_indicator` and `news_article` — types that belong
to other future agents' domains, not this one. Rather than asking
`retrieval_engine` to filter by type (which would mean growing its
contract for one caller — see §3), Fundamental Analyst filters the
returned `ContextPackage.evidence` tuple client-side, keeping only:

- `financial_statement` (primary — this *is* the fundamentals data)
- `corporate_filing`
- `document_section`
- `research_summary`
- `company_profile`

and dropping `technical_indicator` / `news_article` items before
building the prompt. This keeps the module single-responsibility (an
agent whose prompt contains RSI-14 numbers isn't a "Fundamental" analyst
anymore) and keeps prompt-token cost down (§11). The filter is a pure
function over already-fetched data — no second retrieval call.

**Degraded-input handling:** `retrieval_engine`'s semantic leg already
degrades to zero hits on `EmbeddingProviderError` rather than failing
(PROJECT_CONTEXT.md §7/§14). Fundamental Analyst must treat a
context package with zero semantic hits as normal, expected input, not
an error — the bulk of what it actually needs (`financial_statement`,
`corporate_filing`) comes from the structured leg regardless.

---

## 3. Retrieval Contract

The contract between `ai_agents` and `retrieval_engine` is intentionally
the narrowest possible surface:

- **Dependency direction:** `ai_agents` depends on
  `retrieval_engine.service.RetrievalEngineService` (constructor
  injection, built from `get_embedding_provider()` +
  `CompanyRepository` + `RetrievalRepository`, exactly as
  `retrieval_engine/router.py`'s own `get_retrieval_engine_service`
  dependency already constructs it) — reused as-is. This extends the
  existing "cross-module reads go through the owning module's
  repository" rule (PROJECT_CONTEXT.md §13 point 4) one layer up: a
  cross-module *behavior* dependency goes through the owning module's
  **service**, for the same reason — never reach past it into
  `RetrievalRepository` or `knowledge_layer` directly.
- **Zero new methods on `RetrievalEngineService`.** `build_context_package`
  already returns everything needed: ranked, deduplicated `EvidenceItem`s
  with citation metadata, plus the pre-built `context_text`. No new
  retrieval endpoint, no new evidence-type filter parameter, no schema
  change to `ContextPackage`/`EvidenceItem`. This mirrors how `v0.8`
  itself added zero changes to `knowledge_layer` by depending only on its
  already-public `EmbeddingProvider`.
- **Failure propagation:** `retrieve_evidence`/`build_context_package`
  raises `NotFoundError` for an unknown symbol (via `CompanyRepository`).
  Fundamental Analyst does not catch this — it propagates up through
  `BaseAgent.run()` to the Celery task boundary and becomes a normal
  `NiveshError` → `404` response, the same as every other module's
  unknown-symbol handling.
- **`limit` choice:** propose `FUNDAMENTAL_EVIDENCE_LIMIT = 30`, larger
  than retrieval_engine's own `DEFAULT_LIMIT = 20`, since fundamentals
  analysis plausibly wants more than one financial-statement period and
  several filings in view at once, and because the client-side type
  filter (§2) will drop a nontrivial fraction of whatever comes back
  (technical indicators, news). This number is a starting guess, not
  empirically tuned — flagged the same way `RECENCY_HALF_LIFE_DAYS = 180`
  was flagged in v0.8: a documented, deliberate placeholder.
- **No changes to `retrieval_engine`'s stateless/deterministic-scoring
  guarantees** (PROJECT_CONTEXT.md §13 point 1b) are implied or required
  by this design.

---

## 4. Prompt Architecture

Two-message structure (system + user), matching the standard chat-model
message API shape, stored as versioned constants — never built by
string-concatenating live data into a single ad hoc blob.

```
ai_agents/agents/fundamental/
    prompts.py       # SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, PROMPT_VERSION
```

**System prompt** (`FUNDAMENTAL_ANALYST_SYSTEM_PROMPT`, fixed constant):
defines role ("You are a fundamental equity research assistant..."),
hard boundaries (no buy/sell/hold language, no price targets, no
personalized advice, must not state any fact not present in the supplied
evidence, must say "insufficient evidence" rather than infer or
estimate when evidence is thin), and the exact output JSON shape (§6),
requested via the provider's structured-output mode where available
(§5) *and* restated in the prompt text as a redundant safeguard.

**User prompt** (`USER_PROMPT_TEMPLATE`): a short deterministic task
instruction ("Analyze the fundamentals of {symbol} using only the
evidence below. Cite every claim by its [n] reference.") followed
**verbatim** by `ContextPackage.context_text` — the citation-annotated
plain-text block `retrieval_engine.normalization.build_context_text`
already produces. Reusing it directly (rather than re-rendering evidence
into a new format) is deliberate: `context_text`'s `[n]` numbering
becomes the single citation index space both the LLM and the
post-processing validator (§7) agree on, so there is exactly one place
evidence-to-text formatting happens, not two.

**Versioning:** `PROMPT_VERSION = "fundamental-v1"` is recorded on every
`AgentFinding`/`FundamentalAnalysisResult` produced. Prompt text will
change over time (tuning, bug fixes); a versioned constant means past
findings remain interpretable against the prompt that produced them —
the same "know what produced this row" instinct behind
`embedding_model`/`embedding_dimensions` being stored alongside every
`KnowledgeEmbedding` row.

**No multi-turn/conversation state.** One `run()` call = one system +
one user message = one response. This matches the stateless philosophy
already established for `retrieval_engine` (§13 point 1b), extended
here to mean "one agent invocation is one shot," not a chat session —
simpler to reason about, test, and cost-bound.

---

## 5. LLM Provider Abstraction

Mirrors the existing provider/factory/DTO pattern exactly
(PROJECT_CONTEXT.md §8), the same shape `knowledge_layer`'s
`EmbeddingProvider` already established for the project's first paid
external API:

```
ai_agents/providers/
    base.py          # LLMProvider (ABC), LLMCompletion (frozen dataclass)
    exceptions.py    # LLMProviderError, LLMResponseParsingError
    factory.py       # get_llm_provider() -> LLMProvider
    <concrete>_provider.py
```

```python
@dataclass(frozen=True)
class LLMCompletion:
    raw_text: str
    parsed_json: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]
    ) -> LLMCompletion: ...
```

- `LLMProviderError(NiveshError)` — 502, same shape as
  `EmbeddingProviderError`, covers network/HTTP/auth failures.
- `LLMResponseParsingError(LLMProviderError)` — a **new failure mode**
  this codebase hasn't needed before: the HTTP call succeeded but the
  response body isn't valid JSON, or doesn't match the requested schema.
  Kept as a distinct subclass (not folded into the generic error)
  specifically so the service layer can log/handle "couldn't reach the
  model" differently from "model responded but the output was
  unusable" — the second case is the one hallucination-prevention (§9)
  and error-handling (§10) most care about distinguishing.
- `providers/factory.py`'s `get_llm_provider()` is the one place a
  concrete class is chosen — same rule as every other factory (§13
  point 3): `service.py` must import only `LLMProvider`, never a
  concrete class or vendor SDK.
- **Implementation approach:** `httpx.AsyncClient` directly against the
  chosen vendor's chat/completions endpoint, no vendor SDK dependency —
  the same "reuse the one HTTP library the project already has" choice
  `knowledge_layer`'s `OpenAIEmbeddingProvider` and
  `document_intelligence`'s `HttpDocumentExtractionProvider` both made
  (§8). Request structured/JSON-mode output at the API level if the
  chosen vendor supports it (e.g. OpenAI's `response_format:
  json_schema` on `gpt-4o`-class models) — this is a load-bearing choice
  for §9, not a nice-to-have: catching schema drift at the API boundary
  is strictly better than only catching it after the fact in Python.
- **New config settings** (`config.py`, same idiom as `OPENAI_API_KEY`/
  `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS` added in v0.7):
  `LLM_MODEL: str`, `LLM_MAX_OUTPUT_TOKENS: int`,
  `LLM_TEMPERATURE: float` (low — e.g. `0.1` — is the recommended
  default: this is financial analysis, not creative writing, and low
  temperature directly supports determinism and reduces hallucination
  variance, §9). Whether a new `LLM_API_KEY` is needed or the existing
  `OPENAI_API_KEY` is reused depends on the vendor decision (see "Open
  Decisions" at the end).

---

## 6. Expected JSON Output Schema

Owned by the module itself (`ai_agents/agents/fundamental/schemas.py`),
**not** `ai_agents/schemas.py` — that file is the orchestrator's
job-status API shape (`AnalysisRequest`/`AnalysisJobStatus`), a
different layer; each agent should own its own result schema the same
way every domain module owns its own `schemas.py`.

```python
class FundamentalMetricAssessment(BaseModel):
    metric: str                    # e.g. "revenue_growth_yoy"
    observation: str               # evidence-grounded statement, no advice language
    citation_refs: list[int]       # 1+ indices into context_text's [n] citations

class FundamentalAnalysisResult(BaseModel):
    company_symbol: str
    summary: str                            # 2-4 sentences, no buy/sell/hold language
    strengths: list[FundamentalMetricAssessment]
    concerns: list[FundamentalMetricAssessment]
    financial_health_assessment: str        # qualitative synthesis, not a recommendation
    evidence_sufficiency: Literal["sufficient", "partial", "insufficient"]
    confidence_score: float                 # 0..1, see §8 — NOT purely LLM-reported
    citations: list[CitationRef]            # resolved, see §7
    caveats: list[str]                      # e.g. "no financial statements on file"
    prompt_version: str
    model_used: str
    generated_at: datetime
```

Requested from the LLM via structured-output mode (§5) using this same
shape (minus the fields Python computes itself — `confidence_score`,
`citations` resolution, `model_used`, `generated_at`, `prompt_version`
are populated after the call, not asked of the model). After parsing,
the payload is **re-validated with this Pydantic model regardless of
provider-level enforcement** — belt-and-suspenders, since provider-side
structured output is a strong but not absolute guarantee. A validation
failure here raises `LLMResponseParsingError`, handled per §10.

**Relationship to the existing `AgentFinding` contract:** today's
`AgentFinding` (`agents/base.py`) is `{agent_code, summary,
confidence_score, evidence_ids: list[str]}` — too thin to carry the
structured shape above. Proposed **additive** change (backward
compatible, extends rather than replaces):

```python
@dataclass
class AgentFinding:
    agent_code: str
    summary: str
    confidence_score: float
    evidence_ids: list[str]
    detail: dict[str, Any] | None = None   # NEW — agent-specific structured payload
```

`FundamentalAnalystAgent.run()` populates `detail =
FundamentalAnalysisResult(...).model_dump()`, `evidence_ids` from the
resolved citations' `(source_type, source_id)` pairs, and
`confidence_score`/`summary` mirrored from the structured result. This
keeps `BaseAgent`'s contract usable by an orchestrator that only cares
about the common envelope, while not discarding the richer payload a
caller that *does* care (this module's own API, §14) can still read.

---

## 7. Citation Model

Citations are not free text — they are a closed, checkable reference
system, reusing identity `retrieval_engine` already establishes rather
than inventing a new one:

- `context_text`'s `[n]` numbering (built by
  `retrieval_engine.normalization.build_context_text`, already shipped)
  is the **only** citation vocabulary the LLM is given. The prompt
  instructs it to cite claims strictly by these indices.
- A `CitationRef` model resolves each index back to the underlying
  evidence identity already defined in `retrieval_engine`:

```python
class CitationRef(BaseModel):
    index: int
    source_type: str      # reuses retrieval_engine.models.EVIDENCE_SOURCE_*
    source_table: str
    source_id: uuid.UUID
    title: str
    evidence_date: date | None
```

  built by zipping the LLM's `citation_refs` indices against the
  `ContextPackage.evidence` tuple's positions (1-indexed, matching
  `build_context_text`'s `enumerate(evidence, start=1)`) — a pure,
  deterministic post-processing function, no LLM involvement.
- **Out-of-range citation index = deterministic guard, not a soft
  warning.** If the model returns `citation_refs=[7]` but only 5
  evidence items were in the prompt, index `7` cannot be resolved — that
  specific `FundamentalMetricAssessment` is dropped from
  `strengths`/`concerns` (not the whole result) and a caveat is appended
  ("1 unverifiable claim was removed"). This is a zero-cost, fully
  deterministic hallucination guard (§9) — it requires no second LLM
  call, just Python.
- **Empty `citation_refs` = rejected at validation time.** A
  `FundamentalMetricAssessment` with zero citations makes an unsupported
  claim by definition — `validation.py` (new module, following house
  convention of a per-module `validation.py` raising a domain error)
  drops it the same way, rather than accepting it as a lower-confidence
  statement.

---

## 8. Confidence Scoring

**Explicit design position: LLM self-reported confidence is not
trusted alone.** An LLM stating "I am 90% confident" is not a measured
quantity — it is more text generation, and treating it as ground truth
would be exactly the kind of ungrounded number this platform's
research-only, explainability-first posture (§0) argues against. Confidence
is instead a **combination** of a deterministic, pre-LLM signal and a
bounded LLM-reported signal:

1. **`evidence_confidence` (deterministic, computed before the LLM
   call, in Python):** a function of what actually came back from
   `retrieval_engine` — e.g., a weighted score rewarding presence of at
   least one `financial_statement` item (heaviest weight — this is the
   core fundamentals signal), presence of recent `corporate_filing`/
   `document_section` items, and penalizing staleness (age of the most
   recent `financial_statement`). This mirrors `retrieval_engine`'s own
   precedent of deterministic, explainable scoring (its recency-decay
   formula) rather than a learned model — same house philosophy, applied
   one layer up.
2. **`llm_reported_confidence` (bounded, secondary):** the model may
   still report a per-metric confidence in its structured output, but it
   is clamped to `[0, 1]` and never allowed to *raise* the final score
   above what `evidence_confidence` supports — only to lower it (e.g. if
   the model itself flags an assessment as speculative even though
   evidence was technically present).
3. **Final `confidence_score`** = a simple, documented function of the
   two — proposed starting point: `min(evidence_confidence,
   normalized_llm_confidence)`, flagged explicitly (matching
   `RECENCY_HALF_LIFE_DAYS`'s precedent) as a deliberate simplification
   for a first version, not empirically validated, to be revisited once
   there is real output to look at.
4. **Deterministic floor:** if zero `financial_statement` evidence items
   are present, `evidence_confidence` is forced to a low fixed floor
   (e.g. `0.1`) and `evidence_sufficiency` is forced to `"insufficient"`
   **regardless of what the LLM says** — this is not a case where the
   model gets to argue it has enough information; it structurally
   doesn't. This is also directly relevant to today's real sandbox state:
   PROJECT_CONTEXT.md §14 notes no company has ever had
   `sync_company_financials` run in this sandbox, so this floor is not a
   hypothetical edge case — it is the *expected* first-run condition for
   whichever company this is first tested against, unless a financials
   sync is run beforehand.

---

## 9. Hallucination Prevention Strategy

Defense in depth — no single layer is trusted to carry all of this, and
the document is explicit that **none of this makes hallucination
impossible**, only substantially mitigated, the same honesty
PROJECT_CONTEXT.md's "Known Limitations" sections already model for
every other module's real limitations.

1. **Evidence-grounded system prompt** (§4): explicit instruction to
   state only what's in the supplied evidence, and to say "insufficient
   evidence" rather than infer, estimate, or use outside/pretrained
   knowledge about the company.
2. **Structured output / JSON-schema enforcement at the API level**
   (§5), reducing free-text drift and unparseable responses before
   Python ever sees them.
3. **Citation-index range validation** (§7) — a deterministic,
   zero-LLM-cost check dropping any claim whose citation doesn't resolve
   to a real evidence item actually shown to the model.
4. **No claim without a citation** (§7) — empty `citation_refs` is a
   validation failure for that claim, not a lower-confidence pass.
5. **Low temperature** (§5, e.g. `0.1`) — reduces run-to-run variance for
   a domain where consistency matters more than creativity.
6. **Numeric cross-check against already-persisted data — DEFERRED to a
   fast-follow (confirmed with the user during this planning session,
   not built in this version):** for specific, independently computable
   numeric claims (e.g. "revenue grew 12% YoY"), a deterministic Python
   check could compare the LLM's stated figure against the actual value
   already sitting in `financials`' `FinancialRatio`/`ProfitAndLoss` rows
   (already fetched as part of `financial_statement` evidence) within a
   tolerance band, downgrading a mismatch to a caveat rather than
   trusting it. This remains the single strongest guard against a
   specific, checkable class of hallucination (fabricated numbers), and
   the data is already in Postgres at zero extra ingestion cost — but it
   needs its own small parsing/matching design (extracting which metric
   a sentence refers to), and the decision was to ship the other
   guardrails (citation validation, advice-language filter, evidence
   floor — all below) first and prove the module's basic shape before
   adding it. **This is the module's most consequential known gap at
   launch** and should be the first thing revisited once real output
   exists to design the matcher against.
7. **Deterministic investment-advice language filter** — a fixed
   keyword/pattern check (e.g. flagging "buy", "sell", "should invest",
   "recommend purchasing", explicit price targets) run against every
   text field in the structured output **before** a finding is accepted.
   This is a hard compliance guardrail, not merely a prompt instruction
   — given the platform's explicit "research only, never trades, never
   gives personalized investment advice" identity (§0/§1), this is
   arguably the single most important guard in this whole document, and
   it must not depend solely on the model "remembering" the system
   prompt's instruction. A match causes the run to fail closed (§10),
   not to silently strip the offending sentence and continue.
8. **Evidence-sufficiency short-circuit** (ties into §8's floor): when
   `evidence_confidence` is below a fixed threshold, skip the LLM call
   entirely and return a deterministic "insufficient evidence" finding.
   Also a cost optimization (§11).

---

## 10. Error Handling and Fallbacks

- All new failure modes subclass `NiveshError`
  (`LLMProviderError` → 502, `LLMResponseParsingError` → 502), following
  the existing global-handler convention (§13 point — every domain error
  sets `status_code`/`error_code`, never raises `HTTPException`
  directly).
- **Deliberate divergence from `retrieval_engine`'s degrade-gracefully
  precedent, called out explicitly:** `retrieval_engine`'s `_fetch_all`
  catches a failed semantic leg and continues with structured-only
  results (PROJECT_CONTEXT.md §7/§14) — a reasonable choice there
  because "fewer evidence items" is still an honest, non-fabricated
  result. Fundamental Analyst **must not** apply that same pattern to a
  failed or unparseable LLM call: a "finding" produced without the LLM
  actually running would be a fabricated placeholder, exactly what
  `ai_agents`'s own existing docstring already warns against
  ("fabricated AI output would violate the explainability contract").
  A failed LLM call must surface as an explicit error (502) — it must
  **not** silently degrade into some canned or partially-templated
  finding. This asymmetry (retrieval degrades, reasoning does not) is
  intentional and should be preserved by anyone extending this agent or
  building the next one.
- **Retry policy at the Celery task boundary**, following §9's existing
  house convention: transient LLM failures (timeout, HTTP 429/5xx) are
  retried up to the standard `max_retries=3`, same
  `self.retry(exc=exc)` template every other task uses, including the
  mandatory `finally: await engine.dispose()` (§9's documented
  Windows-event-loop fix, applies identically here — this is a new task,
  it must not skip that line). A `LLMResponseParsingError` is retried
  the same way (consistent with the project's "even imperfect,
  consistency over local optimality" stance on retrying validation-style
  failures, §9) but logged under a distinct message so the two failure
  classes stay distinguishable in logs.
- Investment-advice-language-filter failures (§9 point 7) are treated as
  a **non-retryable** rejection — retrying the identical prompt against
  the identical evidence is unlikely to produce a materially different
  outcome, and this is a compliance gate, not a transient fault; it
  should fail closed and be surfaced distinctly (a dedicated error, e.g.
  `AgentOutputRejectedError`), not silently retried into eventually
  passing.
- `retrieval_engine.NotFoundError` for an unknown symbol simply
  propagates — no special handling needed at this layer.
- Explicit, separately configurable LLM call timeout (distinct from the
  embedding provider's own timeout) — LLM completions are typically
  slower than an embeddings call.

---

## 11. Cost and Token Optimization

- `FUNDAMENTAL_EVIDENCE_LIMIT` (§3) bounds how much evidence enters the
  prompt at all — the primary lever.
- Evidence-type filtering (§2) drops irrelevant items (technical
  indicators, news) before they ever reach the prompt, not just before
  the LLM "uses" them.
- `context_text` already caps each snippet at `MAX_SNIPPET_CHARS = 500`
  (existing `retrieval_engine.normalization` constant) — inherited for
  free; this document does not propose changing that shared constant for
  one caller's benefit.
- **Evidence-sufficiency short-circuit** (§8/§9): skip the paid LLM call
  entirely when there isn't enough evidence to produce a meaningful
  result — return the deterministic "insufficient evidence" finding
  instead. This is the single biggest cost lever available, since it
  avoids paying for a call whose answer is knowable in advance.
- **Model choice** is a live cost/quality tradeoff (a cheaper/smaller
  model vs. a larger reasoning model) — flagged as an explicit decision
  for the user, not assumed here (see "Open Decisions").
- **No response caching in this version**, mirroring `retrieval_engine`'s
  stateless-by-decision precedent (§13 point 1b) — re-running the same
  company through the same evidence would re-pay for a fresh LLM call
  every time. A future version could cache by a checksum of
  `context_text` (the same `content_checksum`-gated-upsert idiom
  `knowledge_layer` already uses to avoid re-embedding unchanged text,
  §4 pattern 5) — noted as a natural v0.10+ optimization, not built
  prematurely without real usage data to justify it.
- `LLMCompletion.prompt_tokens`/`completion_tokens` (§5) are captured
  from every response and logged, so real cost is at least observable
  from day one even though nothing aggregates or bills against it yet.

---

## 12. Extensibility for Future Analysts

`agents/base.py`'s own docstring already names nine intended specialist
agents (Market Data, Financial Analysis, Technical Analysis, Valuation,
News Intelligence, Macro Economy, Risk Analysis, Portfolio Analysis,
Compliance). This design treats Fundamental Analyst's module shape as
the **template** for all of them, not a one-off:

```
ai_agents/
    agents/
        base.py                # existing contract (BaseAgent, AgentContext, AgentFinding)
        fundamental/            # THIS version
            agent.py            # FundamentalAnalystAgent(BaseAgent)
            prompts.py
            schemas.py
            queries.py
            validation.py
        technical/               # future — same shape
        valuation/                # future — same shape
        ...
    providers/                  # SHARED across all agents — one LLMProvider abstraction
        base.py
        exceptions.py
        factory.py
        <concrete>_provider.py
```

- **`providers/` is module-level, shared by every future agent** — not
  duplicated per agent. This mirrors `retrieval_engine` reusing
  `knowledge_layer`'s single `EmbeddingProvider` instead of building a
  second implementation (§8 precedent): every specialist agent shares
  one LLM plumbing layer, and supplies only its own prompts/schema/
  evidence-filtering logic.
- **Per-agent extensibility seam:** the "canonical query constant +
  evidence-type allowlist" pair (§2) is proposed as the standard shape
  every future agent defines for itself — e.g. Technical Analyst would
  define its own query string and keep only `technical_indicator`
  evidence; News/Sentiment would keep only `news_article`. This requires
  zero changes to `retrieval_engine` per new agent, the same "extend the
  catalog, not the schema" spirit already established for
  `research/models.py`'s `SourceType` (§13 point 6).
- **`AgentFinding.detail`** (§6's proposed additive field) is generic
  (`dict[str, Any]`) specifically so each future agent can define its
  own richer result schema (a `TechnicalAnalysisResult`,
  `ValuationResult`, etc.) without requiring another change to the
  shared `AgentFinding` dataclass.
- Confidence scoring's two-part shape (§8: deterministic evidence
  coverage + bounded LLM signal) is proposed as a reusable pattern, not
  something unique to fundamentals — though the specific
  `evidence_confidence` formula will necessarily differ per agent (a
  Technical agent's "do I have enough evidence" question looks at
  indicator recency/coverage, not financial statement presence).

---

## 13. Integration with the Future Investment Committee

Deliberately minimal in this document, consistent with PROJECT_CONTEXT.md
§17's explicit caution that "this document should not be read as having
pre-approved any particular `ai_agents` design" beyond what's actually
specified:

- `InvestmentCommitteeOrchestrator.request_analysis` stays exactly as it
  is today — raising `NotImplementedYetError`. This version does not
  touch `orchestrator.py`.
- The only thing this design commits to is that `FundamentalAnalystAgent`
  is **callable the same way any future orchestrator would call it**:
  `await FundamentalAnalystAgent().run(AgentContext(company_id=...,
  trigger_type=...))` → `AgentFinding`. Nothing about this version
  assumes or requires a particular orchestrator design, a Findings Store
  schema, cross-agent conflict resolution, or weighted scoring — all of
  that remains genuinely unscoped, per §17, and should get its own
  architecture-review pass when it's actually taken up.
- The one forward-looking commitment worth stating plainly: because
  `AgentFinding` is the return type `run()` produces today, whatever a
  future Findings Store looks like, it will need to be able to persist
  `AgentFinding`'s shape (including the new `detail` field) — this
  design does not build that store, but it also does not produce output
  that would need reshaping to fit one later.

---

## 14. API Design

**Existing surface, unchanged:** `POST /reports` (`ai_agents/router.py`)
stays exactly as-is — orchestrator-level, still `501` until the
orchestrator exists. This version does not touch it.

**New surface — direct agent invocation**, needed because the
orchestrator that would otherwise be the only caller doesn't exist yet,
and this agent needs to be independently testable/reviewable per the
task's own "review before implementation" framing:

- `POST /agents/fundamental/{symbol}` — following the exact convention
  every `.../generate/` route in this codebase already uses
  (PROJECT_CONTEXT.md §16: "`.../generate/...` routes always return
  `202` with `{symbol, status: "queued", task_id}` and enqueue a Celery
  task — they never do the work inline"). An LLM call is slow and costs
  real money — exactly the profile every existing async route already
  exists to handle; this should not become the one synchronous
  exception.
- `GET /agents/fundamental/{symbol}` — fetch the most recent completed
  result, mirroring `GET /knowledge/{symbol}` / `GET /technical/
  {symbol}/latest`'s "read what a prior async job produced" shape.

**Decision confirmed (this planning session): findings will be
persisted.** Every existing `GET /{module}/{symbol}`-style endpoint in
this codebase reads from a table that module's own `POST .../generate/`
or `.../sync/` route already wrote to; `ai_agents` currently has **zero
database presence** — no `models.py`, no migration. Persisting
Fundamental Analyst's result makes `GET /agents/fundamental/{symbol}`
work the same way every other `GET` in this codebase does, and gives
`ai_agents` its first-ever migration — a deliberate divergence from
`retrieval_engine`'s stateless choice (§13 point 1b of
PROJECT_CONTEXT.md), justified because a *finding* is a durable analysis
result worth looking back on, unlike a retrieval call, which is a
transient lookup over evidence every other module already owns.

Proposed shape for the new `agent_findings` table (for implementation-
time review, not finalized here): `company_id` (FK → `companies.id`),
`agent_code` (e.g. `"fundamental_analyst"` — reuses `AgentFinding
.agent_code`), `result_json` (the full `FundamentalAnalysisResult`
payload), `prompt_version`, `model_used`, `confidence_score`,
`evidence_sufficiency`, `created_at`. Versioning pattern: closer to
`technical_intelligence`'s "upsert-recomputed, not an immutable fact"
pattern (§4 pattern 4) than to `research`'s append-only pattern — a
re-run against fresher evidence supersedes rather than amends the prior
finding, so `ON CONFLICT DO UPDATE` on `(company_id, agent_code)` is the
natural fit, one current row per company per agent. Whether a sibling
append-only audit table is also warranted (mirroring
`corporate_filings`' current-state-plus-audit-trail pattern, §4 pattern
2) is worth a specific answer at implementation time — findings feeding
a future Investment Committee may need a history, not just "latest,"
but that is speculative without a consumer yet and should not be
built preemptively.

- **No auth required** on either route, consistent with every other
  domain module except `portfolios` (financials/filings/news/technical
  are all unauthenticated today) — Fundamental Analyst's endpoints
  should match that, not introduce a new precedent.
- Response schema: `GET` returns `FundamentalAnalysisResult` (§6)
  directly (or a thin `Read` wrapper around it, matching every other
  module's `<X>Read` schema naming); `POST` returns the standard
  `202` queued envelope, same shape as every other async route.

---

## 15. Testing Strategy

Mirrors the existing per-layer structure exactly
(PROJECT_CONTEXT.md §5's test-layout convention):

```
backend/tests/ai_agents/fundamental/
    test_validation.py        # citation range-check, advice-language filter,
                               # empty-citation rejection — pure functions, no mocks
    test_queries.py            # canonical query constant, evidence-type filter
    test_llm_provider.py       # mocked httpx, following test_openai_provider.py's
                                # exact precedent — never calls a real API in CI
    test_prompts.py            # deterministic prompt assembly from a fixed ContextPackage
    test_service.py            # mocked RetrievalEngineService + mocked LLMProvider —
                                # confidence-score combination, evidence-sufficiency
                                # short-circuit, degrade-vs-fail-closed behavior (§10)
    test_api.py                 # FastAPI TestClient + dependency_overrides
    test_repositories.py        # persistence is confirmed (§14) — real-Postgres
                                 # db_session fixture, same skip-cleanly precedent
                                 # every other test_repositories.py uses
```

**Priority ordering, since this module is safety-critical in a way
prior modules weren't:** the deterministic guard functions (§9) —
citation-index validation, investment-advice-language filtering,
evidence-confidence computation, and (if in scope) the numeric
cross-check — should have the highest test coverage of anything in this
module, including explicit test cases for adversarial-ish LLM output
(a response citing an out-of-range index, a response containing
"I recommend buying," a response with an empty `citation_refs` list) —
these are exactly the inputs the guards exist to catch, and they should
be tested as first-class cases, not incidentally covered.

**LLM provider tests use mocked HTTP responses only** — same precedent
`test_openai_provider.py` already set for the embedding provider; no
test in this suite should make a real paid API call.

**Live E2E verification — flagged as a hard requirement, not optional
this time.** Every version from v0.3 onward has included a live
end-to-end pass against a real company before being declared production
ready (§15 point 6), and v0.7/v0.8 both had to document "the paid
external API call itself was not live-verified" as a known limitation
because no `OPENAI_API_KEY` was available in the sandbox
(PROJECT_CONTEXT.md §14). For Fundamental Analyst, **repeating that same
workaround would leave the entire module's actual reasoning step
unverified** — unlike embeddings (where everything up to the API
boundary could still be meaningfully verified), an unverified LLM call
here means the module's core function was never actually exercised.
Whoever implements this version should treat obtaining a working LLM API
key for at least one real end-to-end pass as a precondition for calling
this "done," not a nice-to-have — this is called out explicitly so it
isn't quietly waived the way it understandably was for v0.7/v0.8's
lower-stakes embedding calls.

**Regression check:** confirm zero changes were needed to
`retrieval_engine`, `knowledge_layer`, or any other existing module —
consistent with the "No regressions introduced" bar every prior version
has been held to.

---

## Decisions Confirmed This Planning Session

Settled via explicit user confirmation before any implementation begins,
the same rhythm v0.7 (embedding provider, vector storage) and v0.8
(retrieval persistence) both followed:

1. **Findings persistence — CONFIRMED: persist.** A new
   `agent_findings` table (`ai_agents`'s first migration) backs
   `GET /agents/fundamental/{symbol}`, per §14's proposed shape.
2. **Numeric cross-check against stored financials — CONFIRMED:
   deferred.** Not built in this version; §9 point 6 documents it as the
   module's most consequential known gap at launch and the first thing
   to revisit once real output exists.
3. **LLM vendor/model — NOT YET DECIDED**, deliberately left open rather
   than defaulted. The provider/factory abstraction (§5) is designed so
   this choice is a single `factory.py` line, not an architecture
   change — but a concrete vendor (and model tier, given the cost/
   quality tradeoff in §11) still needs to be chosen before
   `providers/<concrete>_provider.py` can be written. This should be the
   first thing settled when implementation actually starts.

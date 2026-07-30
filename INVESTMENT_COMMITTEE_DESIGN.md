# Investment Committee — Technical Design Document (v1.0 candidate)

**Status:** DRAFT — for review. No code has been written against this
document. Four architecture forks were raised and settled via explicit
user confirmation during this planning session (see "Decisions
Confirmed" at the end): Compliance is **deterministic-only**; the
Committee performs **one shared Retrieval Engine call** distributed to
every specialist (not N independent calls — this has real implications
for the agent contract, worked through in §3/§9 below); Valuation
Analyst **does compute real ratios** (P/E, P/B) via a new synthetic-
evidence step; and a committee decision requires **Fundamental Analyst
specifically** to have succeeded, not just any non-zero number of
specialists. Everything else in this document is still a proposal for
review, following this project's established rhythm (PROJECT_CONTEXT.md
§15 point 3).

**Author context:** produced during a v1.0 planning session, per the
user's instruction: design the Investment Committee — the multi-agent
orchestration layer that sits on top of `ai_agents/agents/fundamental/`
(v0.9, already shipped) — before writing any implementation code.
PROJECT_CONTEXT.md is treated as the architectural source of truth
throughout, and every design choice is checked against what v0.9 already
built, not designed in a vacuum.

---

## 0. Framing: what already exists, and what this document adds

v0.9 shipped exactly one working piece of `ai_agents`: `FundamentalAnalystAgent`
(`BaseAgent` implementation), a shared `LLMProvider` abstraction
(`ai_agents/providers/`), and a persistence layer (`agent_findings` table,
upsert per `(company_id, agent_code)`). `InvestmentCommitteeOrchestrator`
(`ai_agents/orchestrator.py`) was deliberately left untouched — it still
always raises `NotImplementedYetError`. This document designs what fills
that in: multiple specialist agents feeding one synthesis step (the
"Committee Chair"), gated by a compliance review, before anything is
published as a committee-level result.

**Every design decision below is checked against three things that are
already frozen, not renegotiable in this document:**

1. `BaseAgent`/`AgentContext`/`AgentFinding` (`agents/base.py`) — the
   existing contract, including v0.9's additive `AgentFinding.detail`
   field. This document does not propose changing it further.
2. `agent_findings`'s shape (`ai_agents/models.py`) — one row per
   `(company_id, agent_code)`, generic `result_json`. Its own docstring
   already anticipated exactly this reuse: "each future specialist agent
   can persist its own richer shape without a schema change here." This
   document confirms that promise holds and designs zero new tables.
3. The v0.9 guardrail philosophy (PROJECT_CONTEXT.md §13 point 1c):
   confidence is never purely LLM-self-reported; every claim must cite
   real evidence or be dropped; investment-advice language fails the run
   closed; a failed LLM call is never degraded into fabricated output.
   This document extends these principles to a multi-agent setting — it
   does not relax any of them.

**Non-goals of this document (explicitly out of scope for v1.0):**

- Rewriting `FundamentalAnalystAgent` itself — it is reused as-is.
- A new "Findings Store" concept distinct from `agent_findings` —
  §10 shows why the existing table already covers this.
- Portfolio-level or multi-company analysis — every agent in this design,
  the Chair included, still answers one question about one company (see
  §1's Portfolio Analyst discussion for why).
- Real macro-economic data ingestion — see §1's Macro Economy discussion.

---

## 1. Specialist Agents Required

`agents/base.py`'s docstring names nine agents from the original external
architecture docs: Market Data, Financial Analysis, Technical Analysis,
Valuation, News Intelligence, Macro Economy, Risk Analysis, Portfolio
Analysis, Compliance. Checking each against what actually exists in this
codebase today (not against the aspirational list alone) changes the
roster:

| # | Agent | v1.0 status | Why |
|---|---|---|---|
| 1 | **Fundamental Analyst** (= "Financial Analysis") | **Reused, unchanged** | Already shipped in v0.9. Not rebuilt. |
| 2 | **Technical Analyst** | **New** | Absorbs "Market Data" — see below. |
| 3 | **Valuation Analyst** | **New** | See §3's open question on ratio computation. |
| 4 | **News & Sentiment Analyst** | **New** | Explicitly pre-approved for `ai_agents` (PROJECT_CONTEXT.md §12 item 1: "News sentiment analysis... belong here, not in `news_intelligence`"). |
| 5 | **Risk Analyst** | **New** | Synthesizes leverage/volatility/disclosed risk factors across existing evidence types. |
| 6 | **Macro Economy Analyst** | **Out of scope** | No macro data source exists anywhere in this codebase — no ingestion module for interest rates, inflation, GDP, currency. `retrieval_engine` has nothing to retrieve for this agent. Building it now would mean either fabricating unfounded commentary or bolting on an entirely new, unscoped ingestion module — neither is this document's call to make. Flagged for a future version's own explicit spec. |
| 7 | **Portfolio Analyst** | **Out of scope** | Every other agent's `AgentContext` (`company_id`, `trigger_type`, `prior_finding`) is single-company. A real Portfolio Analyst needs portfolio/user-level context (multiple holdings, weights) — a fundamentally different input shape, not a filter on the existing one. It is also explicitly blocked on real auth (PROJECT_CONTEXT.md §12 item 5, §13 point 11: auth is an intentional placeholder). Stretching `AgentContext` to fit this now would be exactly the kind of speculative extension §15's "don't redesign the architecture" guidance warns against. |
| 8 | **Compliance** | **New, but not a `BaseAgent`** | See §6 — it reviews the Chair's synthesized output, not per-company evidence, so it doesn't fit the "one company → one evidence-domain finding" specialist shape at all. |
| — | **Committee Chair** | **New, but not a `BaseAgent`** | Not in the original nine-agent list by that name, but named explicitly in `orchestrator.py`'s own docstring ("runs the LLM synthesis step"). Aggregates specialist findings; does not consume `retrieval_engine` evidence directly (§6). |

**On "Market Data" specifically:** `knowledge_layer`'s own v0.7 spec
explicitly excluded market prices/OHLCV from embeddings ("Do NOT embed:
Market prices, OHLCV data..."), and `retrieval_engine`'s evidence catalog
has no `market_data` source type — only `technical_indicator` (computed
indicators, not raw bars). A standalone "Market Data Agent" would have
no evidence to retrieve and reason over; its natural role (describing
price action, trend, momentum, volume) is already exactly what a
Technical Analyst does over `technical_intelligence`'s computed
indicators. Folding the two together avoids two agents competing over
one evidence source for no informational gain.

**Net v1.0 roster:** Fundamental (reused) + 4 new specialists (Technical,
Valuation, News & Sentiment, Risk) + Chair + Compliance. Macro and
Portfolio are named, explained, and explicitly deferred — not silently
dropped.

---

## 2. Each Agent's Responsibility

- **Fundamental Analyst** (unchanged, v0.9): financial statements,
  profitability, margins, balance sheet strength, cash flow.
- **Technical Analyst**: describes what the company's latest technical
  indicator snapshot shows — trend direction (moving averages),
  momentum (RSI, MACD), volatility (Bollinger Bands, ATR), and volume
  behavior (OBV, volume SMA) — as a factual read of the indicators, not
  a trading signal. Explicitly forbidden from the same investment-advice
  boundary as every other agent (no "this signals a buy").
- **Valuation Analyst**: assesses whether the company's fundamentals
  (earnings, book value) are reflected reasonably in available
  valuation-relevant evidence — see §3 for the open question on whether
  this includes computed ratios (P/E, P/B) or stays qualitative.
- **News & Sentiment Analyst**: characterizes the tone and substance of
  recent news coverage and disclosed corporate developments — factual
  sentiment classification of what evidence says happened (e.g. "a
  contract win was reported," "an earnings miss was reported"), not
  speculation about future price impact.
- **Risk Analyst**: surfaces disclosed and inferable risk factors —
  leverage/liquidity signals from financial statements, explicit "Risk
  Factors" sections from filing document extractions (these exist in
  real extracted data today — document sections are already headed
  things like "Risk Factors"), and volatility context from technical
  indicators.
- **Committee Chair**: synthesizes the specialists' findings (not raw
  evidence — see §6) into one coherent, cited narrative, and surfaces
  where specialists disagree rather than resolving disagreement into a
  false consensus.
- **Compliance**: the final gate before a committee decision is
  considered publishable — re-verifies the Chair's synthesized text
  contains no investment-advice language and that every claim in it is
  still traceable to a real citation (§6, §9).

---

## 3. Evidence Each Agent Receives from the Retrieval Engine

**Decision confirmed (this planning session): one shared Retrieval
Engine call per committee run, not one independent call per specialist.**
The orchestrator calls `RetrievalEngineService.build_context_package`
**exactly once**, with a broad committee-level canonical query
(`COMMITTEE_EVIDENCE_QUERY`, a new constant covering every specialist's
theme at once — "financial fundamentals, valuation, technical momentum,
news sentiment, and risk factors") and a higher `limit` than any single
specialist would need alone (proposed starting point: `60`, since one
pool now has to carry enough evidence for five specialists' filters —
same "documented guess, not empirically tuned" caveat as every other
limit constant in this codebase). This still requires **zero changes to
`retrieval_engine` itself** — the same "extend the catalog, not the
schema" pattern v0.9 already relied on; only *who* calls
`build_context_package` and *how many times* changes.

Each specialist then filters that **one shared, unfiltered evidence
pool** down to its own domain via its own `RELEVANT_EVIDENCE_TYPES`
allowlist — this part is **completely unchanged** from the independent-
retrieval design: each specialist still ends up with its own filtered
subset, still builds its own `[n]`-numbered prompt from that subset
(`§4`/`§7` below are unaffected by this decision — citation numbering,
resolution, and cross-agent dedup all operate on each specialist's
*already-filtered* list regardless of where the unfiltered pool came
from).

| Agent | Evidence types kept from the shared pool |
|---|---|
| Fundamental (unchanged) | `financial_statement`, `corporate_filing`, `document_section`, `research_summary`, `company_profile` |
| Technical | `technical_indicator` only |
| Valuation | `financial_statement`, `corporate_filing` (+ one synthetic ratio item, §3a) |
| News & Sentiment | `news_article`, `research_summary` |
| Risk | `financial_statement`, `document_section`, `corporate_filing` |

**What this costs in real architecture change: a new, additive
constructor parameter on every concrete agent, not a change to
`BaseAgent`/`AgentContext`/`AgentFinding`.** Those three stay exactly as
frozen as §0 states. Instead, each concrete agent class (including
`FundamentalAnalystAgent`, retroactively) gains one new optional
constructor argument:

```python
def __init__(
    self,
    retrieval_service: RetrievalEngineService,
    llm_provider: LLMProvider,
    company_repository: CompanyRepository,
    shared_evidence: list[EvidenceItem] | None = None,   # NEW, optional
) -> None: ...
```

- When `shared_evidence` is `None` (the default), the agent fetches its
  own evidence exactly as `FundamentalAnalystAgent` does today — this is
  what happens for **every direct, standalone invocation**
  (`POST /agents/fundamental/{symbol}` etc., §11), so **v0.9's existing
  behavior, tests, and API contract for Fundamental Analyst do not
  change** when it's called outside a committee run.
- When the orchestrator constructs an agent as part of a committee run,
  it passes the already-fetched shared pool via `shared_evidence`, and
  the agent applies its own `RELEVANT_EVIDENCE_TYPES` filter to that
  instead of calling `retrieval_engine` itself.

This is a real modification to already-shipped v0.9 code
(`FundamentalAnalystAgent.__init__`/`run`), not a pure addition — it
should be called out plainly as its own small, test-covered change at
implementation time, not buried inside the larger committee diff. Every
existing Fundamental Analyst test continues to exercise the
`shared_evidence=None` path unchanged; new tests cover the injected-pool
path.

**Two honest gaps found while designing this, not glossed over:**

1. **Technical Analyst's evidence set is deliberately tiny.**
   `retrieval_engine`'s `_technical_evidence` (v0.8) bundles *all*
   indicator values into **one** evidence item per company (see
   PROJECT_CONTEXT.md §8's `technical_intelligence` entry). Technical
   Analyst will therefore almost always have exactly one citable
   evidence item. This is correct, not a bug — but it means citation
   enforcement here is nearly vacuous (there's only one index to ever
   cite). Worth knowing before assuming the same "N evidence items, some
   get dropped" texture Fundamental Analyst has.
2. **No agent (including Fundamental) has ever had access to the
   company's current price via `retrieval_engine`.** `knowledge_layer`
   deliberately never embeds market prices (§0's non-goals), and
   `retrieval_engine`'s structured legs don't expose one either. This
   only becomes a real problem for Valuation Analyst, since P/E and P/B
   ratios need a price. See the Open Decision in §3a below.

### 3a. The Valuation Analyst ratio question — CONFIRMED: compute real ratios

**Decision confirmed (this planning session): Valuation Analyst computes
real ratios (P/E, P/B), not a qualitative-only narrative.** Before
calling the LLM, the Valuation Analyst additionally fetches
`latest_price`/`latest_trade_date` from the company's Research Dossier
snapshot (`ResearchDossierRepository.get_latest_version` — an existing,
already-used repository elsewhere in this codebase, so this is an
additive dependency, not a new module) and combines it deterministically
(in Python, never the LLM) with already-retrieved financial statement
figures (EPS, book value per share) to compute simple ratios (P/E, P/B).

These computed values are presented to the LLM as a new kind of
**synthetic evidence item** — computed, not retrieved from
`retrieval_engine` — appended to the specialist's own filtered evidence
list before prompt assembly, with its own citation entry pointing back
at the underlying `FinancialStatement` row and the dossier snapshot the
price was drawn from (`source_type="computed_ratio"`, a new constant
scoped to this one agent, not added to `retrieval_engine`'s own
`EVIDENCE_SOURCE_*` catalog — this value is synthesized by the agent
itself, not retrieved, so it does not belong in `retrieval_engine`'s
vocabulary). This is a genuinely new concept (no existing agent presents
computed-not-retrieved values as "evidence") but it is exactly the
numeric-cross-check idea already deferred from Fundamental Analyst
(`FUNDAMENTAL_ANALYST_DESIGN.md` §9 point 6, PROJECT_CONTEXT.md §12 item
11) — this is where it finally gets built, scoped narrowly to Valuation
rather than added retroactively to Fundamental.

If `latest_price` is unavailable (no Research Dossier version exists
yet for the company), the ratio computation is skipped and Valuation
Analyst falls back to the qualitative-only path for that run — a
deterministic, disclosed degradation (a caveat is added), not a hard
failure of the whole specialist.

---

## 4. The JSON Contract Every Agent Returns

v0.9 established a two-layer shape (`FUNDAMENTAL_ANALYST_DESIGN.md` §6):
an `LLM<X>Output` (exactly what's asked of the model) and a full
`<X>AnalysisResult` (the LLM output plus Python-computed
confidence/citations/metadata). Every new specialist follows the same
two layers. **One deliberate generalization for the shared contract**,
proposed for the four *new* agents (Fundamental Analyst's own already-
shipped `strengths`/`concerns` two-list shape is left exactly as it is —
this is not a breaking change to v0.9):

```
LLM<X>Output:
    summary: str
    findings: list[SpecialistAssessment]
    <domain-specific field, e.g. financial_health_assessment>: str
    evidence_sufficiency: "sufficient" | "partial" | "insufficient"
    llm_confidence: float (0..1)

SpecialistAssessment:
    metric: str
    observation: str
    stance: "positive" | "negative" | "neutral"
    citation_refs: list[int]
```

`stance` replaces Fundamental's separate `strengths`/`concerns` lists
with one list plus a classification field — a generalization that fits
domains where a single unified list is more natural (e.g. Valuation's
"fairly valued" is neither a strength nor a concern). The **Committee
layer reads both shapes** when assembling synthesis input (Fundamental's
`strengths`/`concerns` normalize trivially to `stance="positive"`/
`"negative"` respectively) — no rewrite of already-shipped code required.

`<X>AnalysisResult` (the persisted/returned shape) mirrors
`FundamentalAnalysisResult` field-for-field: `company_symbol`, `summary`,
`findings` (or the domain-specific list), `evidence_sufficiency`,
`confidence_score`, `citations`, `caveats`, `prompt_version`,
`model_used`, `generated_at`. This uniformity is what makes the Chair's
job in §6 tractable — it can iterate over any specialist's `detail`
payload with one shared expectation of what's in it.

**Refactor required, not purely additive:** the guardrail functions v0.9
built specifically inside `agents/fundamental/validation.py`
(`check_no_investment_advice`, `filter_valid_citation_refs`,
`drop_unsupported_assessments`, `resolve_citation_refs`) are generic —
nothing about them is Fundamental-specific. This document proposes
promoting them to a shared `ai_agents/guardrails.py`, with every new
specialist (and the Chair and Compliance, §6) importing from there
instead of each duplicating the same regex list and citation logic four
more times. `agents/fundamental/agent.py`'s own imports move to point at
the new location — zero behavior change, full existing test coverage
should catch any regression, but it is real code motion, not a pure
addition, and should be called out plainly at implementation time rather
than buried in a larger diff.

---

## 5. How Disagreements Are Represented

**Disagreement detection is an LLM-reasoning task performed by the
Chair, not a deterministic pass.** Deterministic topic-matching across
genuinely different domains (a Technical Analyst's momentum read vs. a
Fundamental Analyst's growth read) would need real semantic matching to
do well — ironically the kind of similarity search `retrieval_engine`
already has, but repurposing it for cross-agent claim-matching is a
stretch and out of scope here. The Chair is asked, as part of its
structured output, to identify specific points of tension:

```
AgentDisagreement:
    topic: str                      # e.g. "near-term outlook"
    positions: list[DisagreementPosition]

DisagreementPosition:
    agent_code: str
    stance: "positive" | "negative" | "neutral"
    summary: str
    citation_refs: list[int]        # into the Chair's OWN citation list, see §7
```

**What the Committee explicitly does not do:** resolve a disagreement
into a single verdict, a score, or anything resembling "on balance, X."
Surfacing tension between specialists transparently is itself the
useful output — collapsing it into one number would be exactly the kind
of implied recommendation this platform's "research only, never trades"
identity rules out (PROJECT_CONTEXT.md §1/§13 point 1c). A disagreement
is presented as "here is what each specialist said, and where it
diverges," full stop.

**Citation enforcement applies to disagreements too** (§7, §9): every
`DisagreementPosition.citation_refs` entry is range-validated against
the Chair's own citation list, and an unsupported disagreement claim is
dropped the same way an unsupported `SpecialistAssessment` is — reusing
`guardrails.py`'s `drop_unsupported_assessments`-equivalent logic rather
than inventing a parallel mechanism.

---

## 6. How the Committee Chair Synthesizes the Specialists

**The Chair never calls `retrieval_engine` directly.** Its only inputs
are the specialists' own already-persisted `AgentFinding`/`detail`
payloads — each of which already carries resolved, validated citations
(§7). This is a deliberate architectural choice: it bounds the Chair's
evidence surface to what specialists have *already* validated, so the
Chair inherits their citation-validity guarantee transitively instead of
re-deriving it, and it keeps token cost bounded (specialist summaries +
assessments, not five specialists' worth of raw evidence text again).

**Synthesis pipeline** (inside the orchestrator, not a `BaseAgent`):

1. Collect every specialist's persisted `AgentFinding` (only the ones
   that succeeded — see §9 for partial-failure handling).
2. Build a **globally deduplicated citation list** across all
   specialists (§7) — pure Python, no LLM involvement.
3. Build a prompt presenting each specialist's `summary` +
   `findings`/assessments (normalized per §4) + the global citation list,
   with a fixed system prompt carrying the same hard rules Fundamental
   Analyst's system prompt has (evidence-grounded, no advice language,
   JSON-only, cite-or-drop) — reused from `ai_agents/guardrails.py` /
   `prompts.py`, not rewritten per call site.
4. Request structured output (`LLMCommitteeOutput`): an overall
   `summary`, per-theme `findings` (observations that may span multiple
   agents), `disagreements` (§5), and `llm_confidence`.
5. Apply the same citation-range/advice-language guardrails (§7, §9) to
   the Chair's own output before it's treated as valid.
6. Pass the validated draft to Compliance (below) before persisting.

**Compliance is not a `BaseAgent`; it is a gate function over the Chair's
draft, not a per-company evidence-consuming specialist** — it has no
`retrieval_engine` query of its own.

**Decision confirmed (this planning session): Compliance is
deterministic-only.** It re-runs the exact same `check_no_investment_advice`
pattern-based filter (§4's shared `guardrails.py`) against the Chair's
synthesized text specifically — necessary because the Chair's output is
*new* LLM-generated text that hasn't been checked yet, even though every
specialist's own text was already checked before Compliance ever sees
it. No second, nuanced LLM review pass is built for v1.0 — that
possibility is explicitly deferred, not built speculatively, the same
"don't build speculative robustness without real usage signal" reasoning
already applied to `retrieval_engine`'s scoring formula and the deferred
Fundamental Analyst numeric cross-check (PROJECT_CONTEXT.md §12 items
10–11). Revisit only once real false-negative cases from the
deterministic filter are actually observed in production output, not
before.

**Compliance rejection is fail-closed, reusing v0.9's exact precedent**:
if the Chair's draft still contains advice language after synthesis, the
committee run is rejected the same way `InvestmentAdviceDetectedError`
already fails an individual specialist run — logged, not retried, not
silently stripped-and-published. See §9.

---

## 7. Citation Handling Across Multiple Agents

Each specialist numbers its **own** evidence independently (`[1]`,
`[2]`... within its own prompt, per `FUNDAMENTAL_ANALYST_DESIGN.md` §4/§7
— unchanged). When the Chair combines multiple specialists' findings, a
**global citation list** is built deterministically, in Python, before
the Chair's prompt is ever assembled:

```
CommitteeCitationRef:
    global_index: int
    source_agent_code: str      # which specialist originally cited this
    source_type: str
    source_table: str
    source_id: uuid.UUID
    title: str
    evidence_date: date | None
```

Built by unioning every specialist's already-resolved `citations` list
and deduplicating by `(source_type, source_id)` — the exact same
identity-based dedup idiom `retrieval_engine.normalization.deduplicate_and_rank`
already uses at the evidence-retrieval layer, reapplied one level up at
the citation layer. If two specialists both cited the same underlying
evidence row (e.g. Fundamental and Risk both cited the same financial
statement), it collapses to one global citation entry, tagged with both
source agents.

This pre-built, globally-renumbered list is what the Chair's prompt
presents (mirroring how Fundamental's own prompt presents
`retrieval_engine`'s pre-built `context_text` — `FUNDAMENTAL_ANALYST_DESIGN.md`
§4). The **exact same citation-index-validation guardrail applies one
level up**: any `citation_refs` value in the Chair's output outside
`1..len(global_citations)` is dropped from that specific claim, not the
whole synthesis — reusing `guardrails.py`'s
`drop_unsupported_assessments`/`filter_valid_citation_refs`, not a
parallel implementation.

---

## 8. Confidence Aggregation

Continues v0.9's core principle exactly: **never purely LLM-self-reported.**

```
committee_confidence = min(
    mean(specialist.confidence_score for specialist in succeeded_specialists),
    bounded(chair.llm_confidence),
)
```

- The deterministic component is the mean of each **successfully
  completed** specialist's own already-computed `confidence_score`
  (itself already a deterministic-floor-capped value per specialist,
  §8 of `FUNDAMENTAL_ANALYST_DESIGN.md`) — failed specialists are
  excluded and weights renormalize over whoever succeeded, not zeroed
  in place.
- The Chair's own `llm_confidence` can only **lower** this, never raise
  it, the identical rule `compute_confidence_score` already enforces at
  the single-agent level (`agents/fundamental/validation.py`).
- **A useful property that requires no extra logic**: a specialist that
  itself hit the "insufficient evidence" floor (v0.9's
  `EVIDENCE_CONFIDENCE_FLOOR = 0.1`) already contributes a low number to
  the mean by construction — the aggregate naturally reflects a weak
  specialist without the Chair needing to special-case
  `evidence_sufficiency` separately.
- Equal weighting across specialists is proposed as the v1.0 default —
  a deliberate simplification, not empirically validated, in the same
  spirit as `retrieval_engine`'s shared `RECENCY_HALF_LIFE_DAYS` and
  Fundamental's `min()`-based blend. Revisit once real committee runs
  exist to tune against, not before.

---

## 9. Failure Handling If One Specialist Fails

Two distinct rules apply at two distinct levels — this distinction is
the most important design point in this document, so it's stated
explicitly rather than left implicit:

- **Specialist level (unchanged from v0.9):** a specialist's own failed
  or unparseable LLM call never degrades into a fabricated finding — it
  propagates as an error, exactly as `FundamentalAnalystAgent` already
  behaves. This rule does not change for the four new specialists.
- **Committee level (new): partial degradation is acceptable, mirroring
  `retrieval_engine`'s per-leg degradation pattern (PROJECT_CONTEXT.md
  §7) applied one layer up.** If Technical Analyst's LLM call fails but
  Fundamental, Valuation, News, and Risk all succeed, the Chair can
  legitimately synthesize from the four that did — this is not
  fabrication, because the Chair is told explicitly which specialists
  contributed and never pretends the failed one succeeded or fills in
  its absence with invented content. This is different from the
  specialist-level rule in kind, not just degree: at the specialist
  level, "degrading" would mean fabricating evidence-grounded analysis
  that never happened; at the committee level, "degrading" means being
  honest that fewer specialists weighed in, which is exactly the kind of
  disclosed limitation this codebase already values (§0/§9's honesty
  norm, PROJECT_CONTEXT.md §15 point 7).
- **Zero specialists succeeding fails the whole committee run** — there
  is nothing for the Chair to synthesize, and a committee decision
  produced from nothing would be fabricated by definition.
- **A failed Chair synthesis call, or a Compliance rejection, both fail
  the committee run closed** — same reasoning as the specialist-level
  rule: a committee decision produced without the Chair actually
  reasoning, or one Compliance explicitly rejected, must never be
  silently served as if it succeeded.
- **Decision confirmed (this planning session): quorum policy is
  "Fundamental Analyst must always succeed."** Fundamental Analyst is
  treated as the one mandatory specialist — if its own run fails for any
  reason (LLM error, parsing error, or even its own internal
  "insufficient evidence" result, which is a *successful* run producing
  a low-confidence finding, not a failure, and still counts as
  satisfying quorum), the whole committee run fails closed, the same as
  the zero-successes case above. Technical, Valuation, News & Sentiment,
  and Risk are all **optional enrichment** — any subset of them
  (including none) may fail without failing the committee run, and the
  Chair synthesizes from whichever of the four actually succeeded plus
  Fundamental. This reflects Fundamental Analyst's role as the most
  foundational specialist (the only one every other agent's domain
  arguably depends on some notion of) without requiring the strictest
  "all five must succeed" policy, which would make the committee
  needlessly fragile to one non-essential specialist's transient LLM
  failure.

**Celery orchestration model.** Every existing task in `ingestion/tasks.py`
is a simple, single, linear `.delay()` chain (PROJECT_CONTEXT.md §9) —
this codebase has never used Celery's `chord`/`group` fan-out-and-
synchronize primitives. This document recommends **not** introducing
them for v1.0: run the whole committee as **one** Celery task
(`run_investment_committee`) whose `async` body does, in order: (1) one
shared `RetrievalEngineService.build_context_package` call (§3); (2)
construct each specialist's agent with that shared evidence pool
injected, then call each specialist's *existing* `AIAgentsService.run_analysis`
directly in-process (sequentially, or via `asyncio.gather` for
concurrency within the single task — an implementation detail, not an
architecture decision); (3) the Chair synthesis step; (4) the Compliance
gate. This avoids introducing a genuinely new infrastructure pattern for
a first version, and loses little: because each specialist's
`AIAgentsService.run_analysis` **already persists and dossier-links its
own finding immediately upon success** (v0.9, unchanged), a specialist's
progress survives even if a later specialist, the Chair, or Compliance
fails — partial persistence is a free side effect of reusing the
existing per-agent service, not something that requires `chord`'s
independent-subtask durability to achieve. The one thing this ordering
does depend on: the shared evidence pool (step 1) is fetched **once, up
front**, and held in memory for the remainder of the task — if the
committee task itself fails after step 1 but before finishing, the next
run simply re-fetches fresh evidence; nothing about the shared-retrieval
decision requires caching that pool across separate task invocations.

---

## 10. Persistence Strategy

**Zero new tables.** `agent_findings`'s `(company_id, agent_code)`-keyed,
generic-`result_json` shape was explicitly built in v0.9 to support
exactly this (`ai_agents/models.py`'s own docstring: "each future
specialist agent can persist its own richer shape without a schema
change here"). This document confirms that holds:

- Each new specialist (`technical_analyst`, `valuation_analyst`,
  `news_sentiment_analyst`, `risk_analyst`) gets its own row, upserted
  the identical way Fundamental Analyst's is today — new entries in
  `VALID_AGENT_CODES` (`ai_agents/models.py`), nothing else.
- The **Chair's synthesized decision is itself just another row** —
  `agent_code="investment_committee"`. Its `result_json` carries the
  full `CommitteeDecision` payload (summary, findings, disagreements,
  confidence, global citations, caveats) **plus a `source_findings`
  manifest**: `[{agent_code, finding_id, confidence_score,
  evidence_sufficiency}, ...]` — one entry per specialist actually
  synthesized. Because `agent_findings` is upsert-only (a specialist's
  row can be overwritten by a later, unrelated run before anyone reads
  the committee decision again), this manifest is what gives the
  committee decision a lightweight audit trail of *which exact
  specialist finding it was built from* without needing a new versioned
  table — solving the real traceability problem the upsert-only shape
  would otherwise create, without inventing new persistence machinery.
- **Compliance's own verdict is also just another row** —
  `agent_code="compliance_review"` — recording what it reviewed and
  its outcome (`approved`/`rejected` + reasons if rejected). This
  preserves an audit trail even when a committee run is blocked, rather
  than the rejection vanishing silently — consistent with this
  project's general "disclosed limitation over silent failure" norm.
- **Research Dossier integration reuses `SOURCE_TYPE_AGENT_FINDING`
  as-is** — no new source type needed. The Chair's decision is linked
  exactly the way any other `agent_findings` row already is (one
  discrete `ResearchSource` row, `reference_id` = the Chair's own
  `AgentFinding.id`). Each specialist continues linking its own
  evidence row via its own existing, unchanged flow; the Chair's run
  adds exactly one more, on top, for the synthesis itself.
- **If real audit requirements later demand true historical snapshots**
  (not just "latest"), that is a future version's own explicit decision
  — an append-only sibling table, the same "pattern 2" shape
  `corporate_filings`/`financials` already use (PROJECT_CONTEXT.md §4) —
  not something to build speculatively now.

---

## 11. API Endpoints

The existing `/reports` route group (`ai_agents/router.py`) was always
scoped as the orchestrator-level surface — `POST /reports` already
exists (`AnalysisRequest{company_id, force_refresh}` → `202` +
`AnalysisJobStatus{job_id, status}`), currently ending in `501`. This
document proposes making it real, keeping its existing schema
unchanged:

- **`POST /reports`** — unchanged request/response shape. Triggers
  `run_investment_committee` (§9). Standard `202` + queued-task
  envelope, consistent with every other `.../generate/`-style route.
- **`GET /reports/{symbol}`** (new) — returns the full committee bundle:
  the Chair's synthesized decision, the `source_findings` manifest
  (§10) with each contributing specialist's own summary/confidence, the
  Compliance verdict, and `disagreements`. Returns `404` if no committee
  decision exists yet or if the most recent run was rejected by
  Compliance (§9's fail-closed rule extends to reads: a rejected draft
  is never served, the same as if nothing had run — the `404` message
  distinguishes "never run" from "blocked by compliance review" for
  honesty, but the HTTP behavior is identical either way).
- **Each new specialist keeps its own direct-invocation endpoints**,
  mirroring `POST /agents/fundamental/{symbol}` /
  `GET /agents/fundamental/{symbol}` exactly:
  `POST|GET /agents/technical/{symbol}`,
  `POST|GET /agents/valuation/{symbol}`,
  `POST|GET /agents/news-sentiment/{symbol}`,
  `POST|GET /agents/risk/{symbol}`. Even with the orchestrator now
  real, independent invocation remains valuable for testing/debugging
  one specialist without paying for a full committee run — the same
  reasoning `FUNDAMENTAL_ANALYST_DESIGN.md` §14 already gave, still
  valid.
- **Compliance gets no direct endpoint** — it has no per-company
  evidence-retrieval story of its own (§6), so there is nothing
  meaningful to invoke it against standalone. Its verdict is only ever
  visible via `GET /reports/{symbol}`'s bundle.
- **No auth required** on any of these, consistent with every module
  except `portfolios` (PROJECT_CONTEXT.md §14's existing convention).

---

## 12. Testing Strategy

**Per-specialist tests mirror Fundamental Analyst's own suite exactly**
(`FUNDAMENTAL_ANALYST_DESIGN.md` §15), one folder per new agent under
`ai_agents/agents/<name>/`: `test_validation.py` (or shared-guardrail
import tests once `guardrails.py` exists), `test_queries.py`,
`test_prompts.py`, `test_agent.py` (mocked `RetrievalEngineService` +
mocked `LLMProvider`), `test_api.py`.

**New orchestrator-level tests**, the genuinely new surface area this
document adds:

- `test_guardrails.py` — the promoted shared module (§4): citation
  range-checks, advice-language filtering, unsupported-claim dropping,
  now exercised independent of any one agent.
- `test_orchestrator.py` — mocked specialist services (`AIAgentsService`
  instances or their `run_analysis` methods), exercising: all-succeed
  synthesis, partial-failure degradation among the four optional
  specialists (§9), a failed Fundamental Analyst run correctly failing
  the whole committee closed (the confirmed quorum policy), and
  zero-successes hard failure. Also covers the shared-retrieval wiring
  specifically (§3): one mocked `RetrievalEngineService.build_context_package`
  call feeding into every specialist's injected `shared_evidence`
  parameter, confirming each specialist still filters its own correct
  subset from the one shared pool.
- `test_synthesis.py` — the Chair's own pure-Python pieces:
  global-citation-list construction and dedup (§7), disagreement
  structure validation, confidence aggregation (§8) — all testable
  without a real LLM, mirroring how Fundamental's `test_validation.py`
  tests its guardrails as pure functions.
- `test_compliance.py` — the deterministic re-check path (§6), and the
  fail-closed rejection behavior at the task layer (§9), mirroring how
  `test_agent.py` already tests `InvestmentAdviceDetectedError`.
- `test_repositories.py` — real Postgres, confirming multiple
  `agent_code` values (specialists + `investment_committee` +
  `compliance_review`) coexist correctly under the existing
  `(company_id, agent_code)` unique constraint with zero schema changes,
  and that the Research Dossier gets exactly one additional discrete
  evidence row for the Chair's decision.
- **Live E2E verification, same honest constraint as v0.9**: without a
  real `OPENAI_API_KEY`, the full pipeline should be verified live
  against real Postgres data with every specialist's `LLMProvider`
  stubbed (the same technique v0.9's own live verification used —
  `FUNDAMENTAL_ANALYST_DESIGN.md`/PROJECT_CONTEXT.md §14) — confirming
  the fan-out, partial-degradation, citation-renumbering, and
  compliance-gate logic all work against genuine evidence identities,
  even though real model output quality stays unverified until a key is
  available.

---

## Decisions Confirmed This Planning Session

Settled via explicit user confirmation before any implementation begins,
the same rhythm v0.7, v0.8, and v0.9 each followed:

1. **Compliance mechanism (§6) — CONFIRMED: deterministic-only.** No
   second LLM review pass in v1.0; revisit only once real false
   negatives are observed.
2. **Retrieval strategy (§3) — CONFIRMED: one shared retrieval call**,
   distributed to every specialist via a new, additive `shared_evidence`
   constructor parameter on each concrete agent (including a retroactive,
   backward-compatible addition to `FundamentalAnalystAgent`). This is
   the one decision with real implementation weight — flagged explicitly
   at the top of §3 and in the Celery-orchestration note at the end of
   §9, since it touches already-shipped v0.9 code, not just new code.
3. **Valuation Analyst ratios (§3a) — CONFIRMED: compute real ratios**
   (P/E, P/B) via a new deterministic pre-computation step and a
   "synthetic evidence" concept scoped to this one agent.
4. **Quorum policy (§9) — CONFIRMED: Fundamental Analyst must always
   succeed** for a committee decision to be valid; Technical, Valuation,
   News & Sentiment, and Risk are optional enrichment and may fail
   independently without failing the whole committee run.

**Still genuinely open, not decided in this session** (flagged where
they arise, not blocking a first review of this document): the exact
`COMMITTEE_EVIDENCE_QUERY` wording and shared-pool `limit` (§3, a
starting guess like every other limit constant in this codebase);
whether Compliance's deterministic filter should be widened beyond
Fundamental's existing pattern list before v1.0 ships or left identical
and tuned later (§6); and specialist weighting in confidence aggregation
beyond the equal-weight default (§8).

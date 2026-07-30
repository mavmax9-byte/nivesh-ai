# PROJECT_CONTEXT.md

**Purpose of this document:** permanent project memory. A brand-new Claude
conversation (or a new human engineer) should be able to read this file and
continue development with zero loss of context. Written as an onboarding
document for a Senior Staff Engineer joining the project.

Last updated: after v0.9 (Fundamental Analyst).

---

## 1. Project Overview

**Nivesh AI** is an institutional-grade AI investment research platform for
Indian equities (NSE/BSE listed companies).

- **It is explicitly a research/analysis platform, not a trading platform.**
  It never places, modifies, or executes trades. Users act on its research
  manually, through their own brokerage.
- Target domain: Indian equities, INR-denominated, NSE/BSE exchanges,
  Indian fiscal year (April–March) conventions where relevant.
- The full architecture/database/product design was produced *before* any
  code was written and is maintained **outside this repository**.
  `docs/README.md` is an intentional one-paragraph pointer, not a stub to
  fill in — do not create documentation inside `docs/` unless explicitly
  asked. Source code comments frequently cite external doc sections (e.g.
  `docs/v2 04-Multi-Agent-Research-System.md`) that describe design intent
  not implemented yet.
- GitHub: `https://github.com/mavmax9-byte/nivesh-ai` (public repo), single
  branch `main`, no branch protection, direct pushes to `main` have been the
  norm for this project so far (each version was delivered as one commit).

---

## 2. Current Architecture

**Modular monolith**, three-tier:

```
Next.js (frontend, :3000)  →  FastAPI (backend, :8000, /api/v1)  →  PostgreSQL
                                        ↕
                              Celery workers  ↔  Redis (broker db1, results db2, cache db0)
```

- One FastAPI app (`backend/src/nivesh/main.py::create_app`), one Postgres
  database, **one shared SQLAlchemy `DeclarativeBase`** (`core/db.py::Base`)
  that every domain module's `models.py` imports.
- REST only, no GraphQL. All endpoints mounted under `/api/v1` via one
  aggregate router (`api/v1/router.py`).
- Async throughout the backend: SQLAlchemy 2.0 async ORM + `asyncpg`,
  FastAPI async routes, `httpx.AsyncClient` for outbound HTTP.
- Celery for background/ingestion work, Redis as broker + result backend.
- Auth is a placeholder (see §13). Real auth is deferred to a managed
  provider (Clerk/Auth.js per the external architecture docs) and is not
  implemented.
- No AI *reasoning* (no LLM calls, no summarization, no report generation,
  no recommendations) anywhere outside `ai_agents`. This was a hard
  constraint through v0.1–v0.6. **v0.7 narrowly amended it**, after an
  explicit user conversation (see §13, point 1): `knowledge_layer` embeds
  already-persisted text (via a real external embedding API) and
  stores/searches the resulting vectors in Postgres (`pgvector`) — this is
  the first embeddings/vector-DB usage in the codebase, but it is
  retrieval infrastructure only; it does not read, summarize, or reason
  about what it retrieves. **v0.8** added `retrieval_engine`, a second
  retrieval-only module: it combines `knowledge_layer`'s semantic search
  with structured SQL fetches from `financials`/`technical_intelligence`/
  `corporate_filings`/`document_intelligence`/`news_intelligence`,
  deterministically scores, deduplicates, and ranks the result, and
  packages it (plus a citation-annotated text block) for a downstream
  consumer — but, exactly like `knowledge_layer`, it never reasons about
  what it retrieves. **v0.9 is the first version to actually cross the
  reasoning line**, exactly where the platform's architecture always
  intended it to: `ai_agents` is no longer a fully-stubbed placeholder.
  Its first concrete specialist agent, the **Fundamental Analyst**
  (`ai_agents/agents/fundamental/`), calls a real LLM (OpenAI's chat
  completions API, behind an `LLMProvider` abstraction — see §8) to
  analyze a company's financial fundamentals, using `retrieval_engine`'s
  `build_context_package` as its only source of evidence — zero new
  retrieval logic was added anywhere for this. The reasoning itself is
  wrapped in deterministic, non-LLM guardrails (citation-index
  validation, a hard investment-advice-language filter, an
  evidence-coverage confidence floor — see §7/§9/§13) precisely because
  this is now the one place in the codebase where an ungrounded or
  unsafe model output is actually possible; every other module's
  ingestion, normalization, validation, and categorization remains fully
  deterministic (fixed lookup tables, regex/string heuristics,
  arithmetic), and `InvestmentCommitteeOrchestrator` (the multi-agent
  aggregation/synthesis layer) remains unimplemented — v0.9 built one
  working specialist agent, not the Investment Committee (see §12).
- No object/blob storage (S3, MinIO, etc.) anywhere in the stack. This was
  an explicit decision for v0.4 (extracted text goes into Postgres `Text`
  columns) and nothing in `config.py`/`docker-compose.yml` provides one.

---

## 3. Folder / Module Structure

```
nivesh-ai/
├── PROJECT_CONTEXT.md          # this file
├── README.md                   # setup/run instructions
├── docker-compose.yml          # postgres, redis, backend, worker, frontend
├── docker/                     # backend.Dockerfile, worker.Dockerfile, frontend.Dockerfile
├── infra/                      # reverse proxy / future IaC placeholder, not built out
├── scripts/                    # dev.sh, lint.sh, test.sh, migrate.sh
├── docs/                       # intentionally empty pointer -- do not fill in
├── .github/workflows/ci.yml    # ruff + mypy + pytest (backend), lint+typecheck+build (frontend)
├── tests/e2e/                  # Playwright, separate from backend/tests
│
├── backend/
│   ├── pyproject.toml           # uv-managed, see §"Dependencies" below
│   ├── alembic/versions/        # 0001..0008, see §4
│   ├── src/nivesh/
│   │   ├── main.py              # create_app()
│   │   ├── config.py            # pydantic-settings Settings, get_settings()
│   │   ├── dependencies.py      # re-exports get_db, get_redis, get_current_user
│   │   ├── logging_config.py
│   │   ├── core/
│   │   │   ├── db.py            # engine, AsyncSessionLocal, Base, get_db()
│   │   │   ├── celery_app.py    # the one Celery app instance
│   │   │   ├── redis_client.py  # get_redis_client()
│   │   │   ├── security.py      # placeholder auth (CurrentUser, get_current_user)
│   │   │   ├── middleware.py    # CORS + request-id/logging middleware
│   │   │   └── exceptions.py    # NiveshError hierarchy + global handlers
│   │   ├── api/v1/
│   │   │   ├── router.py        # api_v1_router -- mounts every domain router
│   │   │   ├── health.py, version.py
│   │   ├── companies/           # Company + Exchange (core reference domain)
│   │   ├── market_data/         # OHLCV + corporate actions (yfinance dev provider)
│   │   ├── portfolios/          # user holdings (placeholder-auth gated, minimal)
│   │   ├── research/            # Research Dossier -- the cross-domain evidence aggregator
│   │   ├── financials/          # v0.3(a): Financial Statements Engine
│   │   ├── corporate_filings/   # v0.3(b): Corporate Filings Metadata Engine
│   │   ├── document_intelligence/ # v0.4: Document Intelligence Engine
│   │   ├── news_intelligence/   # v0.5: News Intelligence Engine
│   │   ├── technical_intelligence/ # v0.6: Technical Intelligence Engine
│   │   ├── knowledge_layer/     # v0.7: Knowledge Layer (embeddings & semantic retrieval)
│   │   ├── retrieval_engine/    # v0.8: Retrieval Engine (hybrid evidence retrieval)
│   │   ├── ai_agents/           # v0.9: Fundamental Analyst (first concrete agent);
│   │   │                        # InvestmentCommitteeOrchestrator still stubbed
│   │   └── ingestion/tasks.py   # every Celery task, one shared file
│   └── tests/                   # mirrors src/ 1:1 by domain, plus conftest.py
│
└── frontend/src/                # Next.js App Router, TypeScript, Tailwind
    ├── app/                     # page.tsx (dashboard placeholder), portfolio/, stocks/, watchlist/
    ├── components/layout/       # Navbar, Sidebar
    ├── components/ui/           # shadcn-style button, card
    └── lib/                     # api-client.ts (thin fetch wrapper), env.ts, utils.ts
```

Every domain module that ingests external data (`market_data`, `financials`,
`corporate_filings`, `document_intelligence`, `news_intelligence`,
`technical_intelligence`, `knowledge_layer`) has the **identical internal
shape**:

```
<module>/
  models.py            # SQLAlchemy ORM models + module-level string constants
  providers/
    base.py             # abstract Provider (ABC) + frozen dataclass DTOs
    exceptions.py        # ProviderError / NotFoundError subclasses (→ NiveshError)
    factory.py            # get_<x>_provider() -- the ONE place a concrete provider is chosen
    <concrete>_provider.py  # the dev implementation
  normalization.py     # pure functions: provider DTO -> repository-ready dict
  validation.py         # pure functions: raise a domain XxxError on bad data
  repository.py         # DB access only, no business rules
  service.py             # orchestration: validate -> normalize -> persist -> link dossier
  schemas.py             # Pydantic response models
  router.py              # FastAPI routes
```

`companies`, `research`, `portfolios` follow the same repository/service/
router shape but have no `providers/` (they aren't external-data ingesters
themselves — `companies` is populated *by* `market_data`'s sync).

`retrieval_engine` (v0.8) also has no `providers/` for the same reason,
plus one further deviation: its `models.py` defines **no ORM class at
all** — only shared string constants. It owns no database table (see §4)
because it doesn't ingest or persist anything; it only reads evidence
every other module already owns, ranks it, and returns it. Its
`repository.py` is correspondingly unusual: instead of querying a table of
its own, it composes the six sibling repositories (`financials`,
`technical_intelligence`, `corporate_filings`, `document_intelligence`,
`news_intelligence`, `knowledge_layer`) that already own the data it
retrieves — see §6.

`ai_agents` (v0.9) is a different kind of deviation: it is the first
module whose `providers/` package abstracts an LLM (`LLMProvider`, not a
data-ingestion source) and the first module with a two-level internal
structure. `ai_agents/agents/fundamental/` is a self-contained specialist-
agent package (`agent.py`, `prompts.py`, `queries.py`, `schemas.py`,
`validation.py`) sitting *inside* the module, not a sibling top-level
module — the intended template for every future specialist agent named
in `agents/base.py`'s docstring (Technical Analysis, Valuation, News
Intelligence, Macro Economy, Risk Analysis, Portfolio Analysis,
Compliance — see §12). `ai_agents/providers/` stays module-level and
shared across all of them, the same way `retrieval_engine` reuses
`knowledge_layer`'s single `EmbeddingProvider` rather than each future
agent inventing its own LLM plumbing (see §8). `ai_agents/models.py` /
`repository.py` / `service.py` are new for v0.9 — the module had **zero**
database presence before this version (see §4).

### Dependencies (`backend/pyproject.toml`)

Runtime: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `asyncpg`,
`psycopg2-binary`, `pydantic`, `pydantic-settings`, `redis`, `celery`,
`python-dotenv`, `httpx`, `yfinance`, `pandas`, `lxml`, `pypdf`,
`beautifulsoup4`, `pgvector` (added v0.7 — the Python/SQLAlchemy client for
the Postgres `vector` extension; `httpx` is reused for the OpenAI
embeddings HTTP call itself, no `openai` SDK dependency was added, see
§8). Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `pre-commit`. No lock
file — `uv sync` resolves fresh from `pyproject.toml` each time (CI does
the same).

---

## 4. Database Schema Summary

Single Postgres database, single `Base`. Alembic migrations `0001`–`0008`,
applied in order, no branches:

| Migration | Tables |
|---|---|
| `0001_initial_schema` | `exchanges`, `companies`, `historical_ohlcv`, `corporate_actions`, `portfolios`, `holdings` |
| `0002_research_dossier` | `company_research_dossiers`, `research_versions`, `research_snapshots`, `research_timeline`, `research_sources` |
| `0003_financial_statements` | `financial_statements`, `balance_sheets`, `profit_and_loss_statements`, `cash_flow_statements`, `quarterly_results`, `financial_ratios` |
| `0004_corporate_filings` | `filing_categories`, `filing_sources`, `corporate_filings`, `filing_versions` |
| `0005_document_intelligence` | `document_extractions`, `document_sections` |
| `0006_news_intelligence` | `news_articles` |
| `0007_technical_intelligence` | `technical_indicators` |
| `0008_knowledge_layer` | `knowledge_embeddings` (also runs `CREATE EXTENSION IF NOT EXISTS vector`) |
| `0009_agent_findings` | `agent_findings` |

**v0.8 (Retrieval Engine) added no migration and no table** — `retrieval_engine`
owns no persistent state (stateless by explicit user decision during v0.8
planning; see §13 and §14).

**v0.9 (Fundamental Analyst) added `0009_agent_findings`** —
`ai_agents`' first-ever migration and first-ever database table. A
deliberate divergence from `retrieval_engine`'s stateless choice
(explicit `AskUserQuestion` decision during v0.9 planning, see §13 point
1c): a specialist agent's finding is a durable analysis result worth
looking back on (and worth `GET /agents/fundamental/{symbol}` reading
back — see §16), unlike a retrieval call, which is a transient lookup
over evidence every other module already owns.

**`0008_knowledge_layer` requires the Postgres `vector` extension
(pgvector)** — the first migration in this project with an extension
dependency. `docker-compose.yml`'s `postgres` service image was changed
from `postgres:16-alpine` to `pgvector/pgvector:pg16` for this reason (same
Postgres 16 major version, extension pre-installed). A non-Docker local
Postgres needs the `pgvector` server extension installed separately (e.g.
`conda install -c conda-forge pgvector`, which — as of this writing —
resolves against Postgres 16, not 18; verified during v0.7 by downgrading
a local conda Postgres 18 install to 16 to get a compatible build) before
this migration — or `backend/tests/conftest.py`'s `db_session` fixture,
which runs `CREATE EXTENSION IF NOT EXISTS vector` itself before
`create_all` — will succeed.

Key cross-module foreign keys (always plain FK columns, **never** an ORM
`relationship()` reaching into another module — see §13):

```
companies.exchange_id            -> exchanges.id
historical_ohlcv.company_id      -> companies.id
corporate_actions.company_id     -> companies.id
company_research_dossiers.company_id -> companies.id
research_versions.dossier_id     -> company_research_dossiers.id
research_snapshots.version_id    -> research_versions.id
research_sources.version_id      -> research_versions.id
research_sources.reference_id    -> (polymorphic, bare UUID, no FK constraint)
financial_statements.company_id  -> companies.id
corporate_filings.company_id     -> companies.id
corporate_filings.category_id    -> filing_categories.id
corporate_filings.source_id      -> filing_sources.id
filing_versions.filing_id        -> corporate_filings.id
filing_versions.company_id       -> companies.id   (denormalized)
document_extractions.filing_version_id -> filing_versions.id  (UNIQUE)
document_extractions.company_id  -> companies.id   (denormalized)
document_sections.document_extraction_id -> document_extractions.id
news_articles.company_id         -> companies.id
technical_indicators.company_id  -> companies.id
knowledge_embeddings.company_id  -> companies.id
agent_findings.company_id        -> companies.id
```

`knowledge_embeddings.source_id` is a **bare UUID with no FK constraint**,
the same deliberate polymorphic-reference idiom `research_sources
.reference_id` already uses above — it points into whichever table
`source_table` names (`companies`, `corporate_filings`,
`document_sections`, `news_articles`, or `research_versions`, per
`knowledge_layer/models.py`'s `SOURCE_TABLE_BY_TYPE`), not always the same
table, so a real FK isn't possible.

### Two distinct versioning patterns (see §13 — never mix these up)

1. **Pointer + append-only version table** (`research`): a thin mutable
   pointer row (`CompanyResearchDossier`: `current_version_number` counter +
   `last_market_data_watermark` JSONB) plus fully immutable
   `ResearchVersion` rows, one per version, each with its own
   `ResearchSnapshot`. No FK from the pointer to "current version" (would be
   circular) — "latest" is always `ORDER BY version_number DESC LIMIT 1`.
2. **Current-state row + version_number + sibling audit table**
   (`financials`' `FinancialStatement`, `corporate_filings`'
   `CorporateFiling`): the row itself **is** the current state and is
   mutated in place; `version_number` is a plain int incremented on change;
   every change also inserts an immutable sibling row (`FinancialStatement`
   restates as a whole new row per version — actually a hybrid, see code —
   `CorporateFiling`/`FilingVersion` is the cleaner example: `CorporateFiling`
   is mutated in place, `FilingVersion` is the append-only paper trail).
3. **No versioning needed** (`document_intelligence`'s `DocumentExtraction`,
   `news_intelligence`'s `NewsArticle`): a single flat, immutable row is the
   whole record; uniqueness is enforced by a `checksum`/identity constraint
   instead of a version table. `DocumentExtraction` is keyed 1:1 off an
   *already-immutable* `FilingVersion.id`, so a repeat extraction is
   rejected as a **409 conflict** (`DuplicateExtractionError`) — a genuine
   error, not a legitimate re-sync. `NewsArticle` is different: the same
   provider re-serving the same article on every sync is the *normal,
   expected* case (a news feed keeps returning recent history), so a
   repeat is silently skipped (idempotent, following the "unchanged data is
   a no-op" convention in §7) rather than rejected as a conflict. Know
   which of these two behaviors is appropriate before copying either
   pattern into a new module.
4. **Upsert-recomputed, not versioned at all** (`technical_intelligence`'s
   `TechnicalIndicator`): unlike every pattern above, a row here is not an
   immutable fact about something that happened -- it is a *pure function*
   of OHLCV history, so recomputing it is expected to happen repeatedly and
   should simply overwrite the same identity every time
   (`ON CONFLICT DO UPDATE` on `(company_id, trading_date, indicator_name)`,
   the same upsert idiom `market_data`'s own `bulk_upsert` uses -- there is
   no "old value was wrong, new value corrects it" narrative to preserve).
   `TechnicalIndicator` is also this codebase's first entity-attribute-value
   table (one row per company + date + indicator name, rather than one row
   per date with a column per indicator) specifically so new indicators can
   be added as pure data (`INDICATOR_*` constants), never a migration.
5. **Upsert-recomputed, gated by a checksum guard** (`knowledge_layer`'s
   `KnowledgeEmbedding`, added v0.7): like pattern 4, a row is a derived
   value, not an immutable fact, and is upserted (`ON CONFLICT DO UPDATE`
   on `(source_type, source_id)`) rather than versioned. Unlike pattern 4,
   recomputation is *not* unconditional on every run — `content_checksum`
   lets the service layer detect that a source row's text hasn't changed
   since the last run and **skip calling the embedding provider at all**
   for it. The difference from `TechnicalIndicator` is cost: indicator
   math is free CPU, so recomputing everything every run is fine; an
   OpenAI embedding call costs real money and a network round trip, so
   this pattern exists specifically to avoid paying for unchanged content.
   `KnowledgeEmbedding` is this codebase's second entity-attribute-value-
   style table (after `TechnicalIndicator`).
6. **Upsert-recomputed, not gated by a checksum** (`ai_agents`'
   `AgentFinding`, added v0.9): like pattern 4 (`TechnicalIndicator`), a
   row is not an immutable fact but the output of a reasoning pass over
   currently-available evidence, so a re-run supersedes rather than
   amends the prior one — `ON CONFLICT DO UPDATE` on `(company_id,
   agent_code)`, one current row per company per agent, no version
   history table. Unlike `KnowledgeEmbedding` (pattern 5), there is no
   content-checksum guard skipping the (paid) LLM call on unchanged
   input — evidence for a company can change even when no single
   upstream row's checksum does (a new corporate filing arriving changes
   *which* evidence retrieval_engine ranks highest, not any one
   evidence row's own content), so "skip if nothing changed" doesn't
   have a cheap, correct signal to key off yet. Every
   `POST /agents/fundamental/{symbol}` call re-runs the full pipeline,
   including the LLM call — a real cost tradeoff, accepted for this
   foundational version (see §14).

### Reference/lookup tables

`Exchange`, `FilingCategory`, `FilingSource` — a handful of rows each,
always accessed via `get_or_create_by_code(code, name)`, never created ad
hoc by application code.

---

## 5. Coding Conventions

- Python 3.12, fully typed (mypy `disallow_untyped_defs=false` but the
  codebase is typed in practice), `ruff` line-length 100,
  `select = ["E","F","I","UP","B","SIM"]`, `ignore = ["B008"]` (FastAPI
  `Depends()` default-arg pattern).
- **Default to no comments.** Only write one when the *why* is non-obvious
  (a hidden constraint, a workaround, a documented tradeoff). Every module
  in this codebase opens with a docstring explaining *why* it's shaped the
  way it is, often citing the precedent it mirrors — this is the house
  style; new modules should do the same.
- Dataclasses (`@dataclass(frozen=True)`) for provider DTOs and service
  result objects — never leak ORM objects or raw provider payloads across
  layer boundaries.
- Domain errors always subclass `NiveshError` (`core/exceptions.py`), never
  raise `HTTPException` directly from services/repositories. One global
  handler produces `{"error": {"code", "message", "details"}}` for every
  `NiveshError`, and a catch-all handler for anything unhandled → 500.
- Every domain-specific error class sets `status_code` and `error_code`
  as class attributes.
- Tests mirror `src/` 1:1: `tests/<module>/test_<layer>.py`. Every module
  has `test_validation.py`, `test_<provider>.py` (or
  `test_normalization.py`), `test_repositories.py` (real Postgres, see
  below), `test_service.py` (mocked repos via `AsyncMock`), `test_api.py`
  (FastAPI `TestClient`/`AsyncClient` with `dependency_overrides`).
- `backend/tests/conftest.py` imports every module's `models.py` (with
  `# noqa: F401`) purely so `Base.metadata` is fully populated before the
  `db_session` fixture runs `create_all`/`drop_all` against
  `TEST_DATABASE_URL`. **Any new domain module's `models.py` must be added
  here or its tables silently won't exist in the test DB.**
- Repository tests (`test_repositories.py`) use a `db_session` fixture that
  connects to a **real** Postgres (`TEST_DATABASE_URL`), creates all tables,
  runs the test, drops all tables. It **skips cleanly** (does not fail) if
  Postgres is unreachable, so the rest of the suite stays runnable without
  a DB — as of v0.7, this fixture also runs `CREATE EXTENSION IF NOT
  EXISTS vector` before `create_all`, since `KnowledgeEmbedding`'s column
  type needs it (see §4). As of v0.9: **489 tests**, all passing with a
  live Postgres that has the `vector` extension installed, Ruff and mypy
  both clean across the whole `src/` tree. `retrieval_engine` has a
  `test_repositories.py` despite owning no table of its own — it exercises
  `RetrievalRepository`'s delegation to each sibling repository against
  real seeded rows, including the document-section flattening logic (see
  §6). Every version from v0.3 through v0.9 has additionally passed a live
  end-to-end verification pass (real FastAPI + Celery + Redis + Postgres
  stack, a real company symbol, real upstream data) before being declared
  production-ready — see §15 point 6; this has repeatedly caught real bugs
  unit tests alone did not (§11's per-version entries list what was found
  each time). **One exception carried over from v0.7/v0.8**: the live pass
  still cannot exercise a real OpenAI API call (no `OPENAI_API_KEY` in the
  verification sandbox) — v0.9's live pass compensated as far as possible
  by exercising the full real pipeline (real `FundamentalAnalystAgent`,
  real `RetrievalEngineService` against real Postgres data for TCS) with
  only the HTTP call to OpenAI itself swapped for a stub, confirming
  citation-index enforcement, the investment-advice-language guardrail,
  and the schema-parsing guardrail all worked against genuine evidence
  identities (see §14). This still previously meant
  `retrieval_engine`'s *semantic* leg couldn't be exercised live either,
  only its structured SQL leg and its graceful degradation when the
  semantic leg fails (which **was** verified live — see §14).

---

## 6. Repository Pattern

- One repository class per aggregate root (or per small reference table),
  constructor-injected an `AsyncSession`: `def __init__(self, session:
  AsyncSession) -> None`.
- Reference-table repos: `async def get_or_create_by_code(self, code: str,
  name: str) -> Model`.
- **Aggregate-root repos** (`ResearchDossierRepository`,
  `FinancialStatementRepository`, `CorporateFilingRepository`,
  `DocumentExtractionRepository`) use `flush()` for every write except the
  very last one, which calls `commit()` (named `commit_statement`,
  `commit_filing`, `commit_extraction`, `finalize_version` depending on the
  module) — this is a **deliberate exception** to the simpler "each method
  commits its own write" convention used by `companies`/`market_data`,
  justified by needing a parent row + its children to land together or not
  at all.
- These same repos also expose a bare `async def commit(self) -> None:
  await self._session.commit()` passthrough. This exists **specifically**
  so a *service* can durably persist `ResearchDossierRepository`'s
  flush-only evidence writes on the *same shared session* — see §10. This
  is not redundant with `commit_statement`/etc.; it is the mechanism by
  which cross-module evidence-linking becomes durable.
- Bulk writes: `market_data` uses Postgres `ON CONFLICT` upserts
  (`sqlalchemy.dialects.postgresql.insert`). `research` uses plain bulk
  `insert()` for `bulk_create_sources`. `corporate_filings` and
  `financials` use `DISTINCT ON` (Postgres-specific, via
  `select(...).distinct(col)`) for "give me the latest row per period"
  queries — a deliberate, documented, Postgres-only idiom (consistent with
  `ON CONFLICT` being Postgres-only elsewhere).
- Eager loading via `selectinload(...)`, collected into a module-level
  `_DETAIL_OPTIONS` tuple reused across query methods.
- **Cross-module reads go through the owning module's repository**, never
  by a different module's repository querying another module's table
  directly. Example: `document_intelligence`'s service depends on
  `CorporateFilingRepository` (from `corporate_filings`) to look up a
  `FilingVersion` — it does not have its own query against
  `filing_versions`. When a needed read method doesn't exist yet on the
  owning repository, **add one method there** (additive only, never change
  an existing method's signature/behavior). This exact pattern already
  happened twice: `CorporateFilingRepository.get_version_by_id` was added
  for `document_intelligence`, and `ResearchDossierRepository` is
  depended on by `financials`, `corporate_filings`, and
  `document_intelligence` alike.
- **`retrieval_engine`'s `RetrievalRepository` is a new repository shape**
  (added v0.8): every method above assumes a repository queries its
  *own* table. `RetrievalRepository` queries none — it owns no table (see
  §3/§4) — and instead composes six sibling repositories
  (`FinancialStatementRepository`, `TechnicalIndicatorRepository`,
  `CorporateFilingRepository`, `DocumentExtractionRepository`,
  `NewsArticleRepository`, `KnowledgeEmbeddingRepository`), each
  constructed internally from the one `AsyncSession` it's given, and
  exposes one thin read method per source that simply calls into the
  matching sibling method. This still satisfies "cross-module reads go
  through the owning module's repository" above — it just means *every*
  read this particular repository makes is a cross-module read, since
  aggregating already-owned evidence is this module's entire job. No
  ranking/scoring logic lives here; that's `retrieval_engine/service.py`
  and `normalization.py`'s job (§7).
- **`ai_agents`'s `AgentFindingRepository` (v0.9) is back to the
  "ordinary" single-table shape** — it owns `agent_findings` (§4) and is
  the first single-table repository added since `KnowledgeEmbedding`.
  Its `upsert` commits its own write directly (mirroring
  `TechnicalIndicatorRepository.bulk_upsert`'s "every value here is a
  pure recomputation" reasoning), and it also exposes the same bare
  `commit()` passthrough every aggregate-root repository provides, used
  by `AIAgentsService` to durably persist Research Dossier evidence rows
  on the same shared session (§10).

---

## 7. Service Layer Conventions

- One service class per domain, constructor-injected its repositories +
  provider (if any). Owns orchestration only — no SQL, no HTTP.
- Standard sync flow for ingestible domains: `validate() → normalize() →
  check-for-duplicate/unchanged → persist → link into Research Dossier`.
- Every `sync_*`/`extract_*` service method returns a small frozen
  dataclass reporting counts/identity (`MarketSyncResult`, `RefreshResult`,
  `FinancialSyncResult`, `FilingSyncResult`, and the extraction service
  returns the persisted `DocumentExtraction` ORM object directly since
  there's no batch concept there) — **never** raw provider payloads to
  the router/task layer.
- **Idempotent sync convention**: every sync compares an identity+content
  signature against the DB before writing; unchanged data is a silent
  no-op, never an error. Implemented via a pure `is_duplicate_*` function
  per module (`is_duplicate_filing`, `is_duplicate_statement`) fed by
  checksum/value equality. **Exception:** `document_intelligence` does
  *not* follow this — because its identity (`FilingVersion`) is already
  immutable upstream, a repeat extraction is a genuine conflict, not a
  "nothing changed" case, so it raises `DuplicateExtractionError` (409)
  instead of silently skipping. Know which convention applies before
  copying either one into a new module.
- `_persist_filing`/`_persist_statement`-style private methods often need
  to report back *which specific child rows were newly created* so the
  ingestion-task layer can decide what to do next. This was added
  additively to `CorporateFilingsService` for v0.4:
  `FilingSyncResult.synced_filing_versions: tuple[SyncedFilingVersion, ...]`
  — a new field on an existing frozen dataclass, zero change to existing
  consumers. This is the template for "a downstream module needs one more
  piece of information from an upstream sync" going forward.
- Where a service needs to know about the Research Dossier, it depends on
  `ResearchDossierRepository` directly (constructor injection) — it never
  goes through `ResearchPipelineService`. Version *numbering* is the one
  thing no other module is allowed to touch (see §10, §13).
- **`retrieval_engine/service.py` (v0.8) is the first read-only service**
  in this codebase — no `validate → normalize → persist → link dossier`
  flow, because there's nothing to persist (§4) or link (§10). Its
  `retrieve_evidence`/`build_context_package`/`inspect_retrieval` methods
  instead: fetch both retrieval legs, deduplicate/rank
  (`normalization.deduplicate_and_rank`), and return. One convention it
  *does* follow: a failing dependency degrades rather than crashes the
  whole call — `_fetch_all` catches `EmbeddingProviderError` around the
  semantic leg specifically, so a down/misconfigured embedding provider
  never takes structured SQL evidence down with it (see §14). This is a
  new pattern for this codebase (every other module either succeeds or
  raises) worth reusing whenever a future service similarly combines an
  external-dependency leg with an internal-only one.
- **`ai_agents/service.py` (v0.9)'s `AIAgentsService` returns to the
  standard `validate → normalize → persist → link dossier` shape** —
  the "provider" doing the real work is an LLM-backed reasoning agent
  (`BaseAgent`, constructor-injected) rather than a data-ingestion
  provider, and there is no separate normalization step since the agent
  already returns a fully-formed, guard-validated `AgentFinding`
  (validation happens inside the agent itself — see `agents/fundamental/
  agent.py` and §13). One deliberate **asymmetry with `retrieval_engine`'s
  degrade-gracefully pattern above**: a failed or unparseable LLM call is
  **never** degraded into a placeholder finding the way a failed semantic
  leg degrades into "zero semantic hits." Fewer evidence items is still
  an honest result; a "finding" produced without the LLM actually
  reasoning would be fabricated output, which `ai_agents`' own original
  placeholder docstring already ruled out before any of it was
  implemented. `LLMProviderError`/`LLMResponseParsingError` simply
  propagate. A discrete, one-row-per-finding Research Dossier evidence
  row is attached per run (`SOURCE_TYPE_AGENT_FINDING`, §10) — unlike
  `technical_intelligence`/`knowledge_layer`'s aggregate-per-run rows,
  one agent run produces exactly one finding, so the discrete shape
  `corporate_filings`/`document_intelligence`/`news_intelligence` already
  use is the correct fit here, not an aggregate range.

---

## 8. Provider Pattern

- One `ABC` per module in `providers/base.py` (e.g. `MarketDataProvider`,
  `FinancialDataProvider`, `CorporateFilingsProvider`,
  `DocumentExtractionProvider`), plus frozen `@dataclass` DTOs that are the
  **only** shape business logic ever sees — a provider must never leak a
  raw payload (a yfinance dict, an HTTP response, a parsed PDF object)
  past its own file.
- `providers/factory.py` has exactly one function,
  `get_<x>_provider() -> <X>Provider`, and is the **only** place a concrete
  class is chosen. Swapping providers later (a real NSE/BSE feed, a
  commercial data vendor, an OCR-capable extractor) means writing a new
  class + changing one line in `factory.py` — nothing above the provider
  boundary should ever need to change. **One deliberate exception:**
  `technical_intelligence`'s `get_technical_data_provider(ohlcv_repository)`
  takes an argument (an already-open `HistoricalOHLCVRepository`), unlike
  every other factory's zero-arg signature — see below for why.
- `providers/exceptions.py`: a `<X>ProviderError(NiveshError)` (502) and
  usually a `<X>NotFoundError(<X>ProviderError)` (404) subclass, following
  the exact same two-class shape in every module.
- **All current dev providers are honest about their real limitations**,
  and this is a load-bearing project norm, not incidental:
  - `market_data`/`financials`/`corporate_filings` all use **yfinance**
    (no API key, covers NSE/BSE via `.NS`/`.BO` suffixes, good for local
    dev). `corporate_filings`' yfinance provider does **not** have a real
    filings/announcements API to call, so it *derives* filing metadata
    from `get_earnings_dates()` (→ `quarterly_results`) and
    `info["lastFiscalYearEnd"]` (→ `annual_report`); its `source_url` is a
    **generic exchange investor-relations page**
    (`nseindia.com/get-quotes/equity?symbol=X`), not a deep link to an
    actual document, and its `checksum` is a SHA-256 of the metadata tuple
    itself (not a hash of real document bytes, since Sprint 5 explicitly
    never downloads documents). This is documented in the provider's own
    docstring and matters directly for v0.5+ work — **do not assume
    `corporate_filings.source_url` points at a downloadable document.**
  - `document_intelligence`'s `HttpDocumentExtractionProvider` was built
    aware of exactly that limitation: it downloads whatever is at
    `source_url` and dispatches to a PDF parser (`pypdf`, via magic-bytes
    `%PDF-` or `Content-Type` sniffing) or an HTML parser (`bs4` +
    `lxml`, strips `<script>`/`<style>`, returns one page of visible
    text) depending on what actually comes back. **Real NSE pages
    time out for non-browser HTTP clients** (confirmed empirically during
    v0.4 verification — likely anti-bot behavior on NSE's side, not a bug
    in this codebase); the Celery retry mechanism handles this the same
    way it handles any other transient provider failure.
  - `technical_intelligence`'s provider is unlike every other one in this
    codebase: its concrete implementation (`PersistedOHLCVProvider`) does
    not call an external API at all — it reads OHLCV bars `market_data`'s
    own sync has *already persisted* to `historical_ohlcv`, via
    `HistoricalOHLCVRepository`. This directly satisfies the v0.6
    instruction to "reuse the existing Market Data provider... rather than
    creating duplicate market-data fetching logic" — reuse means reusing
    the *data* `market_data`'s provider already fetched, not re-fetching
    it. Because the concrete provider needs a database session,
    `providers/factory.py`'s `get_technical_data_provider` takes the
    caller's already-open `HistoricalOHLCVRepository` as an argument,
    unlike every other factory's zero-arg signature — a deliberate,
    documented, narrow exception, not a precedent to casually extend to
    providers that genuinely call external APIs.
  - `knowledge_layer`'s `OpenAIEmbeddingProvider` (added v0.7) is the
    **first provider in this codebase that requires a paid external API
    key** (`OPENAI_API_KEY`, in `config.py`/`.env` — every other provider
    so far has been free/keyless, like yfinance). It uses `httpx.AsyncClient`
    directly against `POST https://api.openai.com/v1/embeddings` rather
    than adding the `openai` SDK as a dependency, the same "reuse the
    one HTTP library the project already has" choice
    `document_intelligence`'s `HttpDocumentExtractionProvider` made.
    Its `embed(texts: list[str])` method is **batched**, not one call per
    text — inputs are chunked into groups of at most 96 (`_MAX_BATCH_SIZE`)
    per request, since a single generation run can gather many knowledge
    units for one company. A missing/invalid key surfaces as the same
    single `EmbeddingProviderError` every other failure mode does (no
    dedicated "misconfigured" exception type — see the provider's own
    docstring for why). **Not live-verified against the real OpenAI API**
    during v0.7's end-to-end pass (no key was available in the
    verification sandbox) — see §5 and §14.
  - `retrieval_engine` (v0.8) has **no `providers/` package at all** — it
    doesn't call an external API of its own; it reuses `knowledge_layer`'s
    already-existing `EmbeddingProvider` (via
    `knowledge_layer.providers.factory.get_embedding_provider()`) to embed
    a retrieval query, the same provider `knowledge_layer` uses to embed
    source text, not a second implementation. This is a legitimate
    provider-abstraction reuse across modules — `retrieval_engine`
    depends on `knowledge_layer`'s public `EmbeddingProvider` interface,
    never a concrete class — not a violation of point 3 in §13.
  - `ai_agents`'s `LLMProvider` (added v0.9) is the **first provider in
    this codebase that abstracts an LLM chat-completion call**, not an
    embedding call or a data-ingestion fetch — same shape as every other
    provider (`ABC` + frozen-dataclass DTO + `factory.py` + one concrete
    class, `OpenAIChatProvider`), and the same "reuse `httpx`, no vendor
    SDK dependency" choice `OpenAIEmbeddingProvider` already made. It
    reuses the existing `OPENAI_API_KEY` setting (v0.7) rather than
    introducing a second secret — one OpenAI account covers both the
    embedding calls and this chat-completion call. Two exception
    classes, not one (unlike `EmbeddingProviderError`'s single class):
    `LLMProviderError` (the request never produced a usable response —
    network/HTTP/auth failure) and `LLMResponseParsingError` (a response
    came back but its content isn't valid JSON or doesn't match the
    requested schema) — the caller (`agents/fundamental/agent.py`) needs
    to distinguish these, since the second case means the model actually
    ran but the structured-output guarantee didn't hold. Requests the
    vendor's JSON-schema structured-output mode
    (`response_format: {"type": "json_schema", ...}`, `"strict": False`
    — see the provider's own docstring for why `strict` mode was not
    used) so schema drift is caught at the API boundary, not only after
    the fact in Python — this was **not live-verified against the real
    OpenAI API** during v0.9's development (no `OPENAI_API_KEY` in the
    sandbox, the same gap `OpenAIEmbeddingProvider` had at v0.7 — see
    §14). Model/temperature/max-output-tokens are new `config.py`
    settings (`LLM_MODEL="gpt-4o-mini"`, `LLM_TEMPERATURE=0.1`,
    `LLM_MAX_OUTPUT_TOKENS=2000`) — low temperature is deliberate, not a
    default left untouched: this is financial analysis, not creative
    writing, and low temperature directly supports the determinism
    `agents/fundamental/validation.py`'s guardrails depend on (§13).

---

## 9. Celery Architecture

- **Single `celery_app`** (`core/celery_app.py`), **single task-definition
  file** (`ingestion/tasks.py`) — every task the project has, across every
  sprint, lives in this one file. Do not create a second tasks module.
- Every task follows this exact template:

```python
async def _do_the_work(arg: str) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            service = SomeService(...repos constructed from session...)
            result = await service.some_method(arg)
            return {...primitives only, no ORM objects...}
    finally:
        await engine.dispose()

@celery_app.task(name="ingestion.do_the_work", bind=True, max_retries=3, default_retry_delay=60)
def do_the_work(self, arg: str) -> dict:
    try:
        return asyncio.run(_do_the_work(arg))
    except Exception as exc:
        logger.exception("do_the_work_failed", extra={"arg": arg})
        raise self.retry(exc=exc) from exc
```

- **The `finally: await engine.dispose()` is not optional decoration — it
  is fixing a real, previously-shipped production bug.** `engine`
  (`core/db.py`) is a single module-level object shared by every task a
  worker process ever runs, but each task's `asyncio.run()` gives it a
  brand-new event loop. SQLAlchemy's async connection pool must never hand
  out a connection across two different event loops — on Windows, a
  pooled connection's `pool_pre_ping` health check fails deep inside a
  severed proactor socket (`AttributeError: 'NoneType' object has no
  attribute 'send'`) instead of raising a catchable "disconnected" error,
  and the task fails and retries forever. This was found and fixed during
  v0.3 end-to-end verification and must be present in **every** task, not
  just the ones that existed when it was fixed.
- Exceptions that represent a genuine, non-retryable conflict (currently
  `DuplicateExtractionError` from `document_intelligence` and, as of
  v0.9, `InvestmentAdviceDetectedError` from `ai_agents/agents/
  fundamental/validation.py`) are caught **before** the generic `except
  Exception` handler and re-raised without `self.retry(...)` — logged
  and left failed, not retried. `InvestmentAdviceDetectedError` fits the
  same "genuine conflict, not transient" reasoning as
  `DuplicateExtractionError`: retrying the identical prompt against the
  identical evidence would not produce a materially different outcome,
  and it is a compliance rejection, not a fault to paper over by
  retrying it into eventually passing. Every other exception (including
  validation failures like `InvalidFilingDataError`, and — new in v0.9 —
  `LLMProviderError`/`LLMResponseParsingError`) is retried blindly up to
  3 times, even though a permanent validation failure will never succeed
  on retry — this is the established, if imperfect, behavior everywhere
  in this codebase; don't "fix" it locally
  in one module without discussing it, since consistency has been treated
  as more important than local optimality here.
- **Auto-chaining convention**: a successful sync task may trigger the
  next task in the pipeline via `.delay(...)` at the end of its
  celery-task wrapper (not the service). Established chain today:
  `sync_company_market_data` → (always) `refresh_company_dossier`;
  `sync_company_filings` → (only for filing versions the sync *just
  created*, and only for extractable filing types) `extract_filing_document`
  per version; `sync_company_market_data` → (always, alongside
  `refresh_company_dossier`) `generate_technical_indicators` — added v0.6,
  since indicators are computed from the OHLCV bars a market data sync just
  wrote. `sync_company_financials` and `sync_company_news` do **not**
  currently auto-chain into anything -- there is no downstream module that
  consumes financials or news yet. `generate_knowledge_embeddings` (added
  v0.7) is **deliberately not auto-chained from anything** either, even
  though it does have downstream-relevant upstream data (news, filings,
  document extraction, dossier refresh) — unlike every other auto-chain,
  its sources span *four* different upstream modules, and each run can
  make real, paid OpenAI API calls; wiring it to fire automatically after
  every one of those syncs was judged to need an explicit cost-profile
  discussion with the user before assuming it, not decided unilaterally
  during v0.7 (see `knowledge_layer/service.py`'s module docstring). It is
  triggered only via `POST /knowledge/generate/{symbol}` today.
  `generate_fundamental_analysis` (added v0.9) is **also deliberately not
  auto-chained from anything**, for the same cost-profile reason — an LLM
  chat-completion call is real, paid API cost, and this agent's
  fundamentals-relevant evidence (financial statements, filings, document
  sections) already spans multiple upstream syncs; triggered only via
  `POST /agents/fundamental/{symbol}` today.
- Current task inventory (`ingestion.*`): `refresh_company_dossier`,
  `sync_company_market_data`, `sync_company_financials`,
  `sync_company_filings`, `extract_filing_document`, `sync_company_news`,
  `generate_technical_indicators`, `generate_knowledge_embeddings`,
  `generate_fundamental_analysis`.
  **v0.8 (Retrieval Engine) added no Celery task** — it does no
  background/ingestion work, only synchronous reads (see §7), so there
  was nothing to queue.
- Local dev worker command (Windows, since `--pool=prefork` doesn't work
  natively there): `celery -A nivesh.core.celery_app worker --loglevel=info
  --pool=solo --without-mingle --without-gossip --without-heartbeat` — the
  `--without-*` flags were needed because the fakeredis stand-in used for
  local verification (no real Redis available in past sessions) doesn't
  implement the Lua scripting Celery's mingle/gossip startup handshake
  needs; a real Redis doesn't need these flags.

---

## 10. Research Dossier Integration

`research/models.py` is the intentional cross-domain seam every other
module plugs into, and it has been extended **six times** now (v0.3,
v0.4, v0.5, v0.6, v0.7, v0.9) using the identical recipe, with **zero
changes** to `ResearchPipelineService`'s or `ResearchDossierRepository`'s
existing write logic any time:

```python
SOURCE_TYPE_MARKET_DATA = "market_data"
SOURCE_TYPE_FINANCIAL_DATA = "financial_data"        # added v0.3
SOURCE_TYPE_CORPORATE_ACTION = "corporate_action"
SOURCE_TYPE_CORPORATE_FILING = "corporate_filing"     # added v0.3
SOURCE_TYPE_DOCUMENT_EXTRACTION = "document_extraction"  # added v0.4
SOURCE_TYPE_NEWS = "news"                             # populated v0.5
SOURCE_TYPE_TECHNICAL_INDICATOR = "technical_indicator"  # populated v0.6
SOURCE_TYPE_KNOWLEDGE_EMBEDDING = "knowledge_embedding"  # added v0.7
SOURCE_TYPE_AGENT_FINDING = "agent_finding"              # added v0.9
```

`SOURCE_TYPE_NEWS` and `SOURCE_TYPE_TECHNICAL_INDICATOR` had both already
existed as reserved-but-unused constants since Sprint 3 (see the module's
own "extend the catalog, not the schema" docstring, written in
anticipation of exactly this) -- v0.5 and v0.6 were simply the first
versions to actually populate each one. `SOURCE_TYPE_KNOWLEDGE_EMBEDDING`
and `SOURCE_TYPE_AGENT_FINDING` are different: **neither was
pre-reserved**, since nothing before v0.7/v0.9 respectively anticipated
a Knowledge Layer or a concrete specialist agent — each was added fresh,
following the exact same additive recipe (one new constant in
`research/models.py`, one new `Literal` value in `research/schemas.py`,
nothing else in `research/` changes). Either way, **zero changes** to
`ResearchPipelineService` or `ResearchDossierRepository` were needed,
only a plain `from nivesh.research.models import SOURCE_TYPE_X` import
in each module's `service.py`.

`ResearchSource`'s own docstring (research/models.py) also already
specified, since Sprint 3, *how* `technical_indicator` evidence should be
linked once something finally populated it: "High-volume, continuous
evidence (market_data, technical_indicator) is referenced as an aggregate
date range with a record count" — unlike the one-row-per-item linking
`corporate_filings`/`document_intelligence`/`news_intelligence` use.
`technical_intelligence/service.py`'s `_link_to_research_dossier` follows
that pre-existing guidance exactly: one aggregate `ResearchSource` row per
generation run (`range_start`/`range_end` spanning the computed dates,
`record_count` = total indicator values written, `reference_id=None`), not
one row per indicator value — this was decided by precedent already in the
codebase, not invented fresh for v0.6. `knowledge_layer/service.py`'s
`_link_to_research_dossier` (v0.7) follows the same aggregate-per-run
shape for the same reason (one generation run touches many knowledge
units across multiple source types) — but with `range_start`/`range_end`
both `None`, since knowledge units have no natural trading-date range the
way OHLCV-derived evidence does; `record_count` is the number of
embeddings actually written (**not** the number of source units
considered — units skipped via the checksum guard don't count, so
`record_count` reflects real work done, not just a scan size).

The module's own docstring: new sources should **"extend this catalog, not
the schema."** The `SourceType` `Literal` in `research/schemas.py` must be
kept in sync with this set (it's a strict Pydantic Literal — forgetting to
add a new value there breaks the `GET /research/{symbol}` endpoint with a
validation error the moment that evidence type is ever produced; this
happened once already and was caught in review).

**The exact integration recipe every ingesting service follows** (in its
own `_link_to_research_dossier` method, called at the end of a successful
sync):

1. `dossier = await self._dossiers.get_or_create_dossier(company_id)`
2. `latest_version = await self._dossiers.get_latest_version(dossier.id)`
3. If `latest_version is None`: log
   `"<x>_synced_before_research_version"` and **return** — never create or
   bump a version from here.
4. Else: build a list of `ResearchSource` row dicts (`dossier_id`,
   `version_id`, `source_type`, `reference_table`, `reference_id`,
   `range_start`, `range_end`, `record_count`) and call
   `await self._dossiers.bulk_create_sources(rows)` (flush-only).
5. `await self._dossiers.create_timeline_event(dossier_id=..., company_id=...,
   event_type="<x>_synced", description="...", version_id=latest_version.id)`
   (flush-only).
6. **`await self._<own_repo>.commit()`** — the durable commit, on the
   **same shared `AsyncSession`** the dossier repository just flushed on.
   This is why every aggregate-root repository exposes that bare `commit()`
   passthrough (§6) — it is the actual mechanism that makes cross-module
   evidence writes durable.

Version *numbering* is owned exclusively by `ResearchPipelineService`,
driven purely by a market-data watermark comparison. No other module is
ever allowed to create or bump a `ResearchVersion` — they only attach
evidence to whatever version already exists, or skip if none does yet.

**`retrieval_engine` (v0.8) deliberately does not integrate here** — no
new `SOURCE_TYPE_*`, no `_link_to_research_dossier`. Every module before
it that touched this seam was *creating* new evidence (a sync just wrote
new rows); `retrieval_engine` only *reads* evidence every other module
already linked when it was created. Recording "a retrieval call happened"
as dossier evidence would conflate "this fact was established" (what
`ResearchSource` means) with "this fact was looked up," which isn't the
same claim — and would also cut against the stateless decision in §13/§14.

**`ai_agents` (v0.9) integrates here again, and follows the discrete
(not aggregate) linking shape** — `AIAgentsService._link_to_research_dossier`
attaches one `ResearchSource` row per finding (`reference_id` = the
persisted `AgentFinding`'s own id, `range_start`/`range_end=None`,
`record_count=1`), the same one-row-per-item shape `corporate_filings`/
`document_intelligence`/`news_intelligence` use, not the aggregate-range
shape `technical_intelligence`/`knowledge_layer` use. This is a genuine
difference from those two closest precedents: one Fundamental Analyst run
produces exactly one finding (not many indicator values or many
embeddings collapsed into one run), so there is nothing to aggregate —
each finding is its own discrete fact worth its own evidence row, the
same reasoning that makes a single filing or a single news article its
own row rather than part of a range.

---

## 11. Completed Versions (v0.1 – v0.9)

| Version | Delivered | Key modules/tables |
|---|---|---|
| **v0.1 (scaffold)** | Initial commit: FastAPI/Next.js/Docker scaffold, `companies`, `market_data` (yfinance dev provider), `portfolios` (CRUD only), `ai_agents` (fully stubbed), placeholder auth. | `exchanges`, `companies`, `historical_ohlcv`, `corporate_actions`, `portfolios`, `holdings` |
| **Sprint 3 (research)** | Deterministic Research Dossier pipeline: aggregates already-persisted market data into versioned, immutable snapshots. No AI. | `company_research_dossiers`, `research_versions`, `research_snapshots`, `research_timeline`, `research_sources` |
| **v0.3(a) — Sprint 4: Financial Statements Engine** | Ingests/validates/versions/exposes financial statements (balance sheet, P&L, cash flow, quarterly results, ratios computed deterministically). yfinance dev provider. Fixed 2 pre-existing mypy errors in `research` while there. | `financial_statements` + 5 child tables |
| **v0.3(b) — Sprint 5: Corporate Filings Metadata Engine** | Structured catalog of filing *metadata only* (no PDF parsing, no downloading). `CorporateFiling` (current state) + `FilingVersion` (immutable history) pattern. yfinance-derived dev provider (see §8 for its real limitations). During E2E verification of this version, **3 real pre-existing platform bugs were found and fixed**: (1) `market_data/validation.py` crashed on NaN prices instead of filtering them (`decimal.InvalidOperation`); (2) the Celery event-loop/`engine.dispose()` bug (§9); (3) `lxml` was a transitively-relied-on but undeclared dependency. | `filing_categories`, `filing_sources`, `corporate_filings`, `filing_versions` |
| **v0.4 — Document Intelligence Engine** | Deterministic text extraction from filing documents (PDF via `pypdf`, HTML via `bs4`+`lxml` — see §8 for why both), heading/section detection via string heuristics (numbering, ALL CAPS, Title Case — never AI), stored as flat text + structured sections in Postgres. Keyed 1:1 off the immutable `FilingVersion` identity. Auto-triggered off newly-synced filings. During build/review, **3 gaps were found and fixed before release**: (1) the provider was PDF-only despite the real dev-provider data being HTML — added format detection; (2) the API router disambiguated symbol-vs-UUID by runtime type-sniffing on one shared route, inconsistent with every other router's literal-path-segment convention — split into two explicit routes; (3) `FilingVersionRead` didn't expose `id`, making the new endpoints undiscoverable via the API — added it. | `document_extractions`, `document_sections` |
| **v0.5 — News Intelligence Engine** | Per-company news article catalog, ingested via a yfinance-backed dev provider (`Ticker.news`, real publications like Reuters/Bloomberg/Verdict). No versioning (a news article is immutable once published — same "no versioning needed" precedent as `document_intelligence`, see §4); dedup and idempotent re-sync via a `checksum` unique constraint. **Deduplication is scoped per-provider only by explicit user decision** during v0.5 planning: `checksum = sha256(company_id \| provider \| canonicalized_url)`, so the same URL from two different providers is stored as two separate articles rather than merged — true cross-provider identity resolution (recognizing the same real-world story reported under different URLs) is deferred to a future version once a second real provider exists to design that logic against real data. `category` is assigned via a small fixed keyword → category lookup applied to the title (`earnings`/`corporate_action`/`regulatory`/`markets`/`general`) — a deterministic string-heuristic classification, the same "not AI" spirit as `document_intelligence`'s heading detection, not a learned or LLM-based classifier. `SOURCE_TYPE_NEWS` had been reserved-but-unused in `research/models.py` since Sprint 3 specifically for this — v0.5 required **zero changes** to `research/models.py` or `research/schemas.py`. One real bug found during E2E verification: the local Windows dev Postgres cluster used for prior sessions' verification had been `initdb`'d with `WIN1252` server encoding (inherited from the OS locale) instead of UTF8, so it rejected real news text containing non-Latin1 Unicode (smart quotes, zero-width joiners) with `UntranslatableCharacterError`. Confirmed this is a **local sandbox artifact, not an application bug** (the project's `docker-compose.yml` Postgres image, `postgres:16-alpine`, defaults to UTF8) by recreating a UTF8-encoded database in the same cluster and re-verifying successfully — no application code changed for this. | `news_articles` |

| **v0.6 — Technical Intelligence Engine** | Deterministic technical indicators (16 series: SMA 20/50/100/200, EMA 20/50, RSI-14, MACD/Signal/Histogram, Bollinger Bands 20-2, ATR-14, OBV, Volume SMA-20) computed via pandas `rolling()`/`ewm()` from OHLCV bars `market_data` already persisted — no new external fetch (see §8's provider-pattern entry). `TechnicalIndicator` is this codebase's first entity-attribute-value table and its first upsert-only (never versioned) entity (see §4 point 4). **Recompute scope is a bounded trailing window** (300 bars), not full company history — an explicit user decision during v0.6 planning, made to keep generation cost independent of how long a company has been tracked; see §14 for the OBV carry-forward mechanism this required. Auto-triggered after every `sync_company_market_data` run. | `technical_indicators` |
| **v0.7 — Knowledge Layer (Embeddings & Semantic Retrieval)** | The first embeddings/vector-search functionality in the codebase, added after an explicit user conversation amending the previously-absolute "no AI/embeddings/vector DB" rule (see §13, point 1) — scoped narrowly to retrieval infrastructure, no reasoning. Embeds already-persisted text from five source types (company profile, corporate filing metadata, Document Intelligence sections, news articles, Research Dossier version summaries — see `normalization.py` for the deterministic string templates and the honest note on why "corporate filing sections" is interpreted as filing metadata, since `corporate_filings` has no literal per-filing sections) via a real external embedding API (**OpenAI**, `text-embedding-3-small`, 1536 dimensions — chosen over a local `sentence-transformers` model specifically to avoid adding a heavy new ML dependency class to the project) and stores the vectors in Postgres via **pgvector** (chosen over a no-new-infra brute-force-cosine-in-Python approach — both were explicit user decisions during v0.7 planning, made via `AskUserQuestion` before any code was written, per the user's "pause and explain architecture-affecting options" instruction). `KnowledgeEmbedding` is this codebase's fifth persistence pattern and second entity-attribute-value table (see §4 point 5) — upserted, gated by a `content_checksum` guard that skips the (paid) embedding call entirely when a source row's text hasn't changed since the last run. No chunking (text is truncated to ~8000 characters, not split into multiple embeddings — a documented simplification, see §14); no vector index (ivfflat/hnsw) — pgvector's exact distance operators are used directly, scoped per-company via `WHERE company_id = ...`, which is correct and adequately fast at this stage's data volumes (see §14). Semantic search (`GET /knowledge/{symbol}/search`) is the one endpoint in this codebase that makes a live external API call inside a synchronous request (to embed the query text) rather than queuing Celery work — a deliberate, documented exception, not an inconsistency (a search query needs a fresh embedding to compare against; there's no "do it later" version of that). Generation is **not** auto-chained from any upstream sync (unlike `technical_intelligence`) — knowledge sources span four different upstream modules and each run can incur real API cost, so auto-wiring was deliberately left for a future, explicitly-discussed decision; today it's triggered only via `POST /knowledge/generate/{symbol}`. **Not live-verified against the real OpenAI API** during this version's E2E pass — no `OPENAI_API_KEY` was available in the verification sandbox, and the user explicitly chose to document this as a known limitation rather than supply one (see §5, §14); every other part of the pipeline (task dispatch, DB writes, dossier evidence linking, clean error handling on a missing key) was verified live against a real company (TCS). | `knowledge_embeddings` |

| **v0.8 — Retrieval Engine** | The single evidence-retrieval surface intended for future AI agents (`ai_agents`, still unimplemented) — strictly retrieval, ranking, and packaging, no LLM calls, no reasoning, no recommendations (per the v0.8 spec's own explicit boundary). Combines two legs: **semantic** (reuses `knowledge_layer`'s own `EmbeddingProvider` and `KnowledgeEmbeddingRepository`, not a second implementation — see §8) and **structured SQL** (direct fetches from `financials`, `technical_intelligence`, `corporate_filings`, `document_intelligence`, `news_intelligence` — latest/recent facts, no query-text filtering, since a SQL fetch by identity/recency isn't a similarity search). Both legs land on one comparable 0..1 `relevance_score`: semantic hits via cosine similarity, structured evidence via a **deterministic recency-decay** score (`RECENCY_HALF_LIFE_DAYS = 180`, one shared half-life across all structured types — a documented simplification, not empirically tuned). Deduplicates by `(source_type, source_id)` — reusing `knowledge_layer`'s own `SOURCE_TYPE_*` values for the five source types it can also find semantically means an item found via *both* legs (e.g. a news article that's both the most recent story and a semantic match) merges into one item recording both retrieval paths, keeping the higher score. `EVIDENCE_SOURCE_FINANCIAL_STATEMENT`/`EVIDENCE_SOURCE_TECHNICAL_INDICATOR` are the only two new source-type constants, since `knowledge_layer` explicitly never embeds either. A Context Builder (`normalization.build_context_package`) assembles ranked evidence plus a deterministic, citation-annotated plain-text block (`context_text`) suitable as an LLM prompt's evidence section — formatting, not reasoning. **Stateless by explicit user decision during v0.8 planning** (`AskUserQuestion`, before any code was written): no retrieval call is persisted, no new table, no migration (see §4); `GET /retrieval/{symbol}/inspect` gives visibility into a *live* call's per-source fetch counts and pre/post-dedup totals instead. **The semantic leg degrades gracefully** — `EmbeddingProviderError` (e.g. missing `OPENAI_API_KEY`) is caught around just that leg, logged, and treated as zero semantic hits rather than failing the whole request; structured SQL evidence, which needs no external API, is unaffected. This was found and fixed during v0.8's own build (an initial version let a semantic-leg failure take down the entire retrieval call) — before any live E2E pass was run, and reflected in the test suite (`test_retrieve_evidence_degrades_gracefully_when_semantic_leg_fails`). Verified live against real TCS data: structured retrieval, context package assembly, and semantic-leg graceful degradation all confirmed working end-to-end; the semantic leg's actual hit-quality could not be live-verified for the same reason as v0.7 (no `OPENAI_API_KEY` in the sandbox) — see §14. | *(none — stateless, no migration)* |

| **v0.9 — Fundamental Analyst** | The first concrete specialist agent (`ai_agents/agents/fundamental/`), and the first version to actually cross the "no AI reasoning outside `ai_agents`" line `retrieval_engine`/`knowledge_layer` were both built to stop short of (per the v0.9 spec's own explicit boundary, following `FUNDAMENTAL_ANALYST_DESIGN.md`, a full technical design document reviewed with the user before any code was written — see §15 point 3). Analyzes one company's financial fundamentals using **only** evidence from `RetrievalEngineService.build_context_package` (zero new retrieval logic — `retrieval_engine`/`knowledge_layer` needed zero changes), filtered client-side to fundamentals-relevant evidence types (`financial_statement`, `corporate_filing`, `document_section`, `research_summary`, `company_profile` — technical indicators and news are out of scope for this agent, reserved for future specialist agents). Reasoning is behind a new `LLMProvider` abstraction (§8) — **OpenAI `gpt-4o-mini`**, chosen via explicit `AskUserQuestion` during v0.9 planning, reusing the existing `OPENAI_API_KEY` rather than a new secret. The LLM is wrapped in multiple deterministic, non-LLM guardrails, not trusted alone: (1) a **citation-index enforcement** system — every claim must cite a `[n]` reference into the evidence actually shown to the model; an out-of-range/hallucinated index gets that specific claim dropped (not the whole response rejected), and every surviving citation resolves back to a real `(source_type, source_id)` evidence identity; (2) a **hard, pattern-based investment-advice-language filter** (`InvestmentAdviceDetectedError`, buy/sell/hold/price-target patterns) that fails the whole run closed — the single most important guard given this platform's "research only, never trades" identity (§1); (3) a **two-part confidence score** that is never purely the model's self-report — a deterministic, pre-LLM evidence-coverage signal caps what the model's own reported confidence can raise the final score to; (4) a **deterministic "insufficient evidence" short-circuit** — when no `financial_statement` evidence exists at all, the LLM is never called; an explicit insufficient-evidence result is returned instead of guessing, per the v0.9 spec's own explicit requirement. Findings are **persisted** (`agent_findings`, `ai_agents`'s first-ever migration/table — an explicit `AskUserQuestion` decision, chosen over staying stateless like `retrieval_engine`, §13 point 1c) and linked into the Research Dossier as one discrete `SOURCE_TYPE_AGENT_FINDING` evidence row per run (§10). A deliberate asymmetry with `retrieval_engine`'s v0.8 precedent: a failed/unparseable LLM call is **never** degraded into a placeholder finding the way a failed semantic leg degrades into zero hits — that would be fabricated output, which `ai_agents`'s own pre-v0.9 placeholder docstring already ruled out; `LLMProviderError`/`LLMResponseParsingError` simply propagate and retry at the Celery layer, while `InvestmentAdviceDetectedError` fails closed without retry (§9). **Not live-verified against the real OpenAI API** — no `OPENAI_API_KEY` was available in the verification sandbox, the same gap carried from v0.7/v0.8, and the user again explicitly chose to document it rather than supply a key. Compensated as far as possible: the full pipeline was verified live end-to-end against real TCS data in Postgres with only the LLM HTTP call itself stubbed, confirming citation-index enforcement (a hallucinated index dropped, a valid one resolved to a genuine evidence row), the investment-advice filter, and the schema-parsing guardrail all work correctly against real evidence identities; the "insufficient evidence" path was verified **fully live, with zero stubbing at all**, since TCS has no synced financial statements in this sandbox (see §14). | `agent_findings` |

**Test count as of v0.9: 489 passing** (`pytest`, real Postgres with the
`vector` extension installed). Ruff and mypy both clean across the whole
`src/` tree.

Commits (chronological, all on `main`):
`6d5e038` init → `9c8ff36` gitignore → `f616f25` Sprint 4 → `fe5a0e4` ruff
fixes → `d308b17` mypy fixes → `53b1e66` feat(v0.3) corporate filings →
`d3f691c` feat(v0.4) document intelligence → `ae47f82` feat(v0.5) news
intelligence → `084870c` feat(v0.6) technical intelligence → `9b0b621`
feat(v0.7) knowledge layer → `1f8f4ac` feat(v0.8) retrieval engine →
(v0.9 fundamental analyst, see git log for the current hash).

---

## 12. Current Roadmap (v0.10 onwards)

Nothing beyond v0.9 has been scoped or approved yet. Do not start
implementing v0.10 without an explicit spec from the user — this project's
working pattern has consistently been: architecture review first (no code)
→ user confirms scope → implement → self-review → verify → commit/push.
See §17 for the current v0.10 spec status.

**What v0.4 through v0.9 were explicitly building toward**: document
extractions, news articles, technical indicators, a semantic retrieval
index, a hybrid ranked-evidence retrieval surface over all of it, and now
one working specialist agent consuming that surface to actually reason —
exist so a *future* version can build on them. Natural, foreshadowed next
steps, roughly in dependency order:

1. **The rest of the `ai_agents` / Investment Committee layer.** v0.9
   built exactly one specialist agent (`FundamentalAnalystAgent`) and
   left `InvestmentCommitteeOrchestrator.request_analysis` untouched —
   it still always raises `NotImplementedYetError`. Two genuinely
   different pieces of work remain, both still fully unscoped:
   - **More specialist agents** — `agents/base.py`'s docstring already
     names eight more (Market Data, Technical Analysis, Valuation, News
     Intelligence, Macro Economy, Risk Analysis, Portfolio Analysis,
     Compliance). `ai_agents/agents/fundamental/` is the intended
     template each would follow (§3/§12 of `FUNDAMENTAL_ANALYST_DESIGN.md`):
     its own `agent.py`/`prompts.py`/`queries.py`/`schemas.py`/
     `validation.py`, sharing the module-level `LLMProvider` abstraction
     (§8) and the `agent_findings` table (one row per `(company_id,
     agent_code)`, §4) rather than inventing new plumbing per agent.
   - **The orchestrator itself** — aggregating multiple agents' findings,
     detecting conflicts, weighted scoring, an LLM synthesis step, a
     Compliance Agent pass before publication (per `orchestrator.py`'s
     own docstring). Needs a real spec and its own architecture-review
     pass before any code — v0.9 deliberately did not invent a Findings
     Store schema or cross-agent aggregation logic; see
     `FUNDAMENTAL_ANALYST_DESIGN.md` §13 for why that was left
     unscoped rather than guessed at.
   News sentiment analysis / AI summarization of articles, and any
   trading strategy/signal/forecasting logic built on top of
   `technical_intelligence`'s indicator values, both still belong to a
   future specialist agent, not to `news_intelligence` or
   `technical_intelligence` themselves.
2. **A real filings-discovery provider** for `corporate_filings` (NSE/BSE
   announcements API or a commercial vendor) that supplies genuine
   document deep-links — this would make `document_intelligence`'s PDF
   path the common case instead of the fallback (and, downstream, both
   `knowledge_layer`'s `document_section` embeddings and
   `retrieval_engine`'s `document_section` structured evidence would
   actually populate for real companies in this sandbox — see §14), with
   zero changes needed to `document_intelligence` itself (the whole point
   of the provider abstraction).
3. **A second real news provider** for `news_intelligence` (Reuters,
   Economic Times, Moneycontrol, Google News, etc.) — needed before true
   cross-provider duplicate-article identity resolution can be designed
   and validated against real data (see §11's v0.5 entry and §14 for why
   this was deliberately deferred rather than guessed at speculatively).
4. **Real authentication** (`core/security.py` is an explicit,
   documented placeholder — swap for Clerk/Auth.js or similar).
5. **Portfolio analytics** (`portfolios/service.py`'s docstring: "Portfolio
   analytics... are produced by the Portfolio Analysis Agent, not this
   service" — i.e. this is blocked on #1).
6. **Frontend wiring** — the Next.js app currently has placeholder pages
   with "No data yet" copy; `lib/api-client.ts` exists but nothing calls
   the real backend endpoints yet.
7. **Raw document storage** — explicitly postponed in v0.4 (see §13). If
   ever revisited, requires a real infrastructure decision (S3/MinIO) that
   doesn't exist in this stack today.
8. **A pgvector ANN index** (ivfflat/hnsw) for `knowledge_embeddings`,
   once real data volumes make pgvector's current exact/sequential-scan
   search (see §14) worth optimizing — not needed at today's scale.
9. **Auto-chaining `generate_knowledge_embeddings`** from its upstream
   syncs (news, filings, document extraction, dossier refresh), once the
   resulting OpenAI API cost profile has been explicitly discussed with
   the user (see §9's v0.7 entry for why this was deliberately deferred
   rather than assumed).
10. **Revisiting `retrieval_engine`'s scoring formula** — the single
    shared `RECENCY_HALF_LIFE_DAYS = 180` and the plain
    `1 - cosine_distance` semantic score are deliberate, simple choices
    for a foundational version, not empirically validated against real
    retrieval quality (see §13/§14). `ai_agents` (item 1) is now
    consuming this module's output for real via the Fundamental
    Analyst — once a real `OPENAI_API_KEY` is configured and this agent
    has real runs to look at, that's the point to revisit tuning, not
    before, since there was still no real usage signal to tune against
    during v0.9's own development (no live LLM verification — see §14).
11. **A numeric cross-check for the Fundamental Analyst** — comparing
    LLM-stated financial figures against already-persisted `financials`
    data (`FinancialRatio`/`ProfitAndLoss`) as an additional
    hallucination guard, deliberately deferred out of v0.9's scope (an
    explicit `AskUserQuestion` decision during v0.9 planning — see
    `FUNDAMENTAL_ANALYST_DESIGN.md` §9 point 6) in favor of shipping the
    other guardrails (citation enforcement, investment-advice filtering,
    the evidence-confidence floor) first. Flagged in that design doc as
    the module's most consequential known gap at launch — the first
    thing to revisit once real Fundamental Analyst output exists.
12. **Findings caching / cost optimization for `ai_agents`** — every
    `POST /agents/fundamental/{symbol}` call re-runs the full pipeline
    including the LLM call, unlike `knowledge_layer`'s checksum-gated
    skip (§4 point 6). A future version could cache by a checksum of the
    evidence actually shown to the model, the same `content_checksum`
    idiom `KnowledgeEmbedding` already uses — not built in v0.9 without
    real cost data to justify it.
13. **Auto-chaining `generate_fundamental_analysis`** from upstream
    syncs, once its OpenAI API cost profile has been explicitly
    discussed with the user — the same reasoning that kept
    `generate_knowledge_embeddings` (§9's v0.7 entry) and now
    `generate_fundamental_analysis` (§9) manually triggered only, not
    auto-wired, in their first versions.

---

## 13. Architectural Decisions That Must Never Change (without an explicit,
deliberate conversation with the user first)

1. **Determinism everywhere except `ai_agents` — narrowly amended by v0.7,
   v0.8, and (for reasoning itself) v0.9.** No AI *reasoning* (no LLM
   calls, no summarization, no report generation, no recommendations, no
   sentiment analysis, no knowledge graph) anywhere outside `ai_agents`.
   This was an absolute constraint (also covering embeddings/vector
   search/evidence ranking) through v0.1–v0.6, restated explicitly by the
   user for v0.4, v0.5, and v0.6 (v0.5's restatement specifically named AI
   summarization, sentiment analysis, and semantic search as excluded from
   `news_intelligence`; v0.6's specifically named trading strategies,
   buy/sell signals, forecasting, and ML models as excluded from
   `technical_intelligence`). **v0.7 (Knowledge Layer) and v0.8 (Retrieval
   Engine) were deliberate, narrow exceptions to the embeddings/vector-
   search/ranking half of this rule**, each made only after an explicit
   user conversation (the v0.7 spec named it: "This version introduces
   embeddings and vector search only... must not introduce AI reasoning,
   report generation, or investment recommendations"; the v0.8 spec named
   it: "This sprint must not invoke an LLM or generate analysis. It only
   prepares high-quality evidence for future AI agents") — neither was
   allowed to **read, summarize, or reason about** what it retrieved.
   **v0.9 is where reasoning itself was finally, explicitly allowed** —
   but strictly *inside* `ai_agents`, per its own spec's boundary ("Do not
   generate investment advice, buy/sell recommendations, target prices, or
   portfolio guidance"), and wrapped in deterministic, non-LLM guardrails
   precisely because this is now the one place ungrounded model output is
   possible (§7/§9, §1c below). Every module outside `ai_agents` remains
   exactly as deterministic as it always was — v0.7/v0.8/v0.9's existence
   is not a general license to add AI elsewhere; each was one narrowly-
   scoped, explicitly-approved exception, not a precedent to extend
   casually.
1a. **v0.7's specific embeddings/vector-search decisions are themselves
    frozen** (each was an explicit `AskUserQuestion` decision during v0.7
    planning, not a default): embedding provider is **OpenAI**
    (`text-embedding-3-small`) behind the `EmbeddingProvider` abstraction
    (§8) — swappable, but the *choice* of a paid hosted API over a local
    model was deliberate, not incidental. Vector storage is **pgvector**
    in the same Postgres (§4) — chosen over a no-new-infra brute-force-
    cosine-in-Python approach; this is why `docker-compose.yml`'s
    `postgres` image changed to `pgvector/pgvector:pg16` (§4). No chunking
    of long text into multiple embeddings (§14). No auto-chaining of
    `generate_knowledge_embeddings` from upstream syncs (§9). Changing any
    of these is exactly the kind of "architecture-affecting decision" that
    needs a fresh explicit conversation with the user first, not a
    unilateral change during a later version.
1b. **v0.8's specific retrieval decisions are themselves frozen**:
    `retrieval_engine` is **stateless** — no retrieval call is persisted,
    no new table, no migration (an explicit `AskUserQuestion` decision
    during v0.8 planning, chosen over a `RetrievalRun` audit-log table).
    Scoring is deterministic only: semantic hits via cosine similarity,
    structured evidence via a single shared recency half-life
    (`RECENCY_HALF_LIFE_DAYS = 180`) — not a learned ranking model, not
    per-type tuning. Deduplication key is `(source_type, source_id)`,
    reusing `knowledge_layer`'s own `SOURCE_TYPE_*` values where they
    overlap (§10). The semantic leg degrades gracefully on
    `EmbeddingProviderError` rather than failing the whole request (§7).
    Changing any of these needs a fresh explicit conversation with the
    user first, the same as 1a.
1c. **v0.9's specific Fundamental Analyst decisions are themselves
    frozen** (each was either an explicit `AskUserQuestion` decision
    during v0.9 planning or a hard requirement stated in the v0.9 spec
    itself, not a default): LLM provider is **OpenAI `gpt-4o-mini`**
    behind the `LLMProvider` abstraction (§8) — swappable, but the choice
    itself was deliberate. Findings **are persisted** (`agent_findings`,
    §4) — chosen over staying stateless like `retrieval_engine`. A
    numeric cross-check against `financials` data is **deferred**, not
    built in v0.9 (§12 item 11). Confidence is **never purely
    LLM-self-reported** — a deterministic evidence-coverage signal always
    caps the final score (§7/§8 of `FUNDAMENTAL_ANALYST_DESIGN.md`).
    Every claim **must** cite real evidence — an out-of-range/hallucinated
    citation drops that specific claim rather than being silently kept.
    Investment-advice language (buy/sell/hold/price-target patterns)
    **must** fail the whole run closed via a hard pattern-based filter,
    never a soft warning or a stripped-and-continue. A failed/unparseable
    LLM call **must never** degrade into a placeholder finding (§7) — this
    is a deliberate asymmetry with `retrieval_engine`'s v0.8 degrade-
    gracefully pattern, not an oversight; a fabricated "finding" is worse
    than an explicit error. Changing any of these needs a fresh explicit
    conversation with the user first, the same as 1a/1b.
2. **One shared `Base`, one Postgres database.** Never introduce a second
   declarative base or a second database/schema without explicit sign-off.
3. **The provider/factory/DTO abstraction is not optional.** Business
   logic (`service.py`) must never import a concrete provider class or
   a third-party client library directly — only the abstract
   `<X>Provider` type and `get_<x>_provider()`.
4. **Cross-module reads go through the owning module's repository.**
   Never write a raw query against another module's table from outside
   that module. Add a new read method to the owning repository instead
   (additive only).
5. **Cross-module ORM relationships are forbidden.** Cross-module
   references are plain `ForeignKey` columns only — never a SQLAlchemy
   `relationship()` reaching from one module's model into another's (see
   §4/§6). This keeps modules importable independently and avoids import
   cycles.
6. **`research/models.py`'s `SourceType` catalog is additive-only.** New
   evidence sources add a new `SOURCE_TYPE_*` constant + `Literal` value in
   exactly two files (`research/models.py`, `research/schemas.py`) and
   nothing else in `research/` changes. Version *numbering* stays
   exclusively owned by `ResearchPipelineService`.
7. **Every Celery task must `await engine.dispose()` in a `finally` block**
   (see §9) — this is a fix for a real bug, not stylistic.
8. **No object/blob storage.** Extracted/derived text lives in Postgres.
   Raw documents are never persisted anywhere (`document_intelligence`
   discards downloaded bytes immediately after parsing). Introducing
   S3/MinIO/etc. is a deliberate, explicitly-postponed future decision.
9. **Two versioning patterns coexist on purpose** (§4) — pointer+version-
   table (`research`) vs. current-state+version_number+audit-sibling
   (`financials`, `corporate_filings`). Pick the one that matches the new
   domain's actual shape; don't invent a third pattern.
10. **`.claude/settings.local.json` and other local tool config are
    gitignored**, never committed — this was fixed early in the project's
    history and should stay that way.
11. **Auth and portfolio analytics are intentionally unimplemented
    placeholders**, not oversights — do not "helpfully" implement fake
    versions of either.

---

## 14. Known Limitations and Future Improvements

- **`corporate_filings`' dev provider does not produce real document
  links.** `source_url` values are generic exchange investor-relations
  pages, and `checksum` is a metadata fingerprint, not a document hash.
  This is documented, deliberate, and was accounted for when building
  `document_intelligence` (§8) — but any new code that assumes
  `source_url` is a direct filing PDF link will be wrong against the
  current dev data.
- **NSE's website appears to block/timeout non-browser HTTP clients** —
  observed empirically, not yet worked around (no User-Agent spoofing,
  no session/cookie warmup implemented). A real filings provider (§12
  item 1) would likely need to address this properly (or simply use a
  different, more automation-friendly data source).
- **`get_earnings_dates(limit=N)` (yfinance) does not reliably honor
  `limit`** — observed returning more rows than requested during v0.3
  verification. Not a bug in this codebase; just a caveat when reasoning
  about how much history `corporate_filings` syncs per call.
- **No CI-managed Postgres/Redis services** have been confirmed in
  `.github/workflows/ci.yml` as of this writing for the E2E-style
  repository tests — those tests skip cleanly without a reachable
  `TEST_DATABASE_URL`, so CI passing does not by itself prove the
  Postgres-dependent tests ran. Verify `db_session` fixture behavior in CI
  before trusting a green CI run as proof those specific tests executed.
- **No lock file** (`uv.lock` does not exist) — dependency resolution is
  whatever `uv sync` resolves at run time against the `>=` version floors
  in `pyproject.toml`. This has not caused a problem yet but means builds
  are not perfectly reproducible.
- **Windows-specific development quirks** documented in this file (event
  loop/`engine.dispose()`, `--pool=solo` for Celery, fakeredis
  `--without-mingle` flags) are specific to the sandboxed Windows
  verification environment used so far. A Linux/Docker Compose deployment
  (which `docker-compose.yml` already targets) may not hit the same
  issues, but the `engine.dispose()` fix should stay regardless — it is
  correct on any platform, just more silently masked on Linux.
- **Frontend is not wired to the backend at all.** Every page is a static
  placeholder. This is a large, mostly-independent stream of future work.
- **`ai_agents` has zero implementation.** `BaseAgent` defines a contract
  (`AgentContext`, `AgentFinding`) with no concrete specialist agents, and
  `InvestmentCommitteeOrchestrator` always raises `NotImplementedYetError`
  by design (explicitly not stubbed with fake data, per its own
  docstring, "since fabricated AI output would violate the explainability
  contract before it even exists").
- **`news_intelligence` deduplicates per-provider only, by explicit
  design.** `NewsArticle.checksum` folds `provider` into the dedup key, so
  two different providers reporting the same real-world story under
  different URLs are stored as two separate rows, not merged. This was a
  deliberate v0.5 decision (over a fuzzier title/date-based cross-provider
  match) made because there is currently only one real provider in
  production — designing true cross-provider identity resolution now
  would be speculative and unvalidated. See §12 item 2.
- **`news_intelligence`'s yfinance dev provider never populates `author`
  or `full_content`** — `Ticker.news` doesn't expose either field. Both
  columns exist and are nullable specifically so a future richer provider
  can populate them without a schema change.
- **A local Windows dev Postgres cluster can end up with non-UTF8 server
  encoding.** Discovered during v0.5 E2E verification: a conda-installed
  Postgres cluster `initdb`'d in an earlier session inherited `WIN1252`
  encoding from the Windows OS locale, which rejects real-world Unicode
  text (smart quotes, zero-width joiners — both appear in real news
  article summaries) with `asyncpg.exceptions.UntranslatableCharacterError`.
  This is **not** an application bug and does **not** affect the actual
  deployment target — `docker-compose.yml`'s `postgres:16-alpine` image
  defaults to UTF8. If a local non-Docker Postgres install ever throws
  this error, recreate the database with
  `CREATE DATABASE ... TEMPLATE template0 ENCODING 'UTF8'` (or just use
  `docker compose up -d postgres` instead) rather than treating it as a
  code defect.
- **`technical_intelligence` recomputes over a bounded 300-bar trailing
  window, not a company's full price history** — an explicit v0.6 decision
  (over recomputing every indicator across full history on every run),
  made to keep the cost of a single generation run independent of how long
  a company has been tracked. `LOOKBACK_BARS = 300` in
  `technical_intelligence/service.py` is comfortably more than the longest
  window any indicator here needs (SMA-200), leaving generous margin for
  the standard seeding convention used by recursively defined indicators
  (EMA, RSI, MACD, ATR). One consequence: `OBV` (a running cumulative
  total from inception, not a fixed-window calculation) cannot be
  correctly derived from the window alone, so it is carried forward
  explicitly from the last already-persisted value each run (see
  `normalization.py`'s `compute_obv` and its module docstring) rather than
  re-derived — this makes OBV numerically exact across runs *as long as
  generation runs frequently relative to the window size* (true today,
  since it auto-triggers on every market data sync). If a company ever
  goes more than ~300 trading days between generation runs, OBV's
  carry-forward would miss the gap's contribution and silently re-anchor
  from the window's start — an accepted, documented edge case given how
  the window size and auto-trigger cadence are chosen, not a bug to "fix"
  without first reconsidering `LOOKBACK_BARS`.
- **`technical_intelligence`'s `providers/factory.py` deviates from the
  established zero-argument factory signature** every other module uses
  (`get_technical_data_provider(ohlcv_repository)` takes an argument) —
  see §8's technical_intelligence entry for why this is a deliberate,
  narrow exception and not a pattern to extend elsewhere.
- **`knowledge_layer`'s OpenAI embedding calls were not live-verified**
  during v0.7's E2E pass — no `OPENAI_API_KEY` was available in the
  verification sandbox, and the user explicitly chose to document this
  gap rather than supply a key. Everything up to that call boundary
  *was* verified live against a real company (TCS): task dispatch, all
  five source types gathered correctly, DB writes, dossier evidence
  linking (correctly skipped when nothing was generated), and clean
  `EmbeddingProviderError`/502 handling on the missing key, with no data
  corruption. The actual OpenAI HTTP call/response parsing was verified
  only via mocked responses in `test_openai_provider.py`. Whoever first
  configures a real `OPENAI_API_KEY` should do one live
  `POST /knowledge/generate/{symbol}` + `GET /knowledge/{symbol}/search`
  pass before fully trusting this path in production.
- **`knowledge_layer` embeds `corporate_filings` metadata, not real "filing
  sections."** The v0.7 spec asked for "corporate filing sections" to be
  embedded, but `corporate_filings` has no per-filing section/paragraph
  breakdown of its own (only `document_intelligence`'s `DocumentSection`
  does, which v0.7 also embeds separately). `build_corporate_filing_text`
  (`knowledge_layer/normalization.py`) embeds each `CorporateFiling`
  row's own descriptive metadata (title, filing type, reporting period,
  category name) as one text blob instead — a deliberate, documented
  interpretation, not a silent gap. See §8/§11's v0.7 entries.
- **`knowledge_layer`'s `document_section` embeddings are empty in this
  sandbox for the same pre-existing reason `document_intelligence`'s own
  extractions are** — NSE blocks non-browser HTTP clients (see the item
  above and §12 item 2), so `extract_filing_document` never completes for
  real companies here, so there are no `DocumentSection` rows to embed.
  Not a v0.7 regression; confirmed during v0.7's own E2E pass.
- **No chunking of long source text.** `truncate_for_embedding`
  (`knowledge_layer/normalization.py`) truncates any source unit's text to
  ~8000 characters (a conservative proxy for `text-embedding-3-small`'s
  ~8191-token input limit) rather than splitting it into multiple
  overlapping chunks — a long document section loses its tail rather than
  producing several embeddings. Accepted for this foundational version;
  revisit if long-document recall quality becomes a real problem.
- **No pgvector ANN index yet** (see §12 item 8) — `knowledge_embeddings`
  has no `ivfflat`/`hnsw` index; similarity search is an exact,
  sequential scan scoped by `company_id`. Correct and fast enough at
  today's per-company data volumes; would need revisiting only once real
  volumes grow large.
- **`generate_knowledge_embeddings` does not auto-chain from anything**
  (see §9's v0.7 entry and §12 item 9) — triggered only via
  `POST /knowledge/generate/{symbol}` today, a deliberate v0.7 choice to
  avoid uncontrolled OpenAI API cost across four different upstream sync
  paths without an explicit cost-profile conversation with the user first.
- **A local (non-Docker) Postgres needs the `pgvector` extension package
  installed separately**, not just the `pgvector` *Python* package in
  `pyproject.toml` — the two are different things (a Postgres server
  extension vs. a SQLAlchemy client library). During v0.7 verification,
  the local conda Postgres install had to be **downgraded from 18 to 16**
  because conda-forge's `pgvector` extension build available at the time
  targets Postgres 16, not 18 — a local-sandbox compatibility detail, not
  an application constraint (`docker-compose.yml`'s
  `pgvector/pgvector:pg16` image doesn't have this problem).

- **`retrieval_engine`'s semantic leg was not live-verified against the
  real OpenAI API** for the same reason as `knowledge_layer`'s (§5/§14
  above) — no `OPENAI_API_KEY` in the verification sandbox. What *was*
  verified live against real TCS data: structured SQL retrieval across
  all five structured source types, the Context Builder's citation-
  annotated `context_text` output, `GET /retrieval/{symbol}/inspect`'s
  per-source fetch counts, and — specifically — graceful degradation of
  the semantic leg (confirmed live: a request with no API key configured
  returned full structured evidence with zero `"semantic"` items, rather
  than failing). Semantic-hit quality and cross-leg deduplication (an
  item found via both legs merging into one) were verified only via
  mocked/unit tests (`test_service.py`), not live.
- **`retrieval_engine`'s recency scoring means older-but-authoritative
  evidence can be crowded out by a `limit`-bounded result set of fresher
  but less significant items** — observed during v0.8's live pass: a
  10-item request for TCS returned the technical snapshot and 9 recent
  news articles, with none of the company's 10 fetched corporate filings
  making the cut (they were fetched correctly, per
  `GET /retrieval/{symbol}/inspect`, just outscored on recency). This is
  the expected, working behavior of a pure recency-based structured
  score (§13 point 1b) — not a bug — but is worth knowing before assuming
  a small `limit` always surfaces a *representative* cross-section of
  evidence types; a caller that needs guaranteed per-type coverage should
  request a larger `limit` or call `GET /retrieval/{symbol}/inspect` to
  see everything fetched before ranking.
- **`retrieval_engine`'s `financial_statement` evidence type was not
  exercised live** — no company in the verification sandbox has synced
  financial statements (`sync_company_financials` was never triggered for
  TCS in any session's E2E pass so far), so `get_financial_statements`
  correctly returned zero rows live; the code path is covered only by
  `test_service.py`/`test_repositories.py`'s mocked/seeded tests. Not a
  v0.8 regression — financials sync for TCS has simply never been run in
  this sandbox.
- **`document_section` evidence is empty in this sandbox for the same
  pre-existing NSE-blocking reason `knowledge_layer`'s own
  `document_section` embeddings are** (see the `document_intelligence`
  item above and §12 item 2) — confirmed again during v0.8's own E2E
  pass, not a new gap.

- **`ai_agents`'s `LLMProvider` (`OpenAIChatProvider`) was not
  live-verified against the real OpenAI API** during v0.9's development —
  the same gap `OpenAIEmbeddingProvider` had at v0.7, no `OPENAI_API_KEY`
  in the sandbox. Unlike v0.7/v0.8 (where the untestable call was one leg
  of a larger, still-mostly-verifiable pipeline), an unverified LLM call
  here would have left the Fundamental Analyst's entire core function
  unexercised — so v0.9's live E2E pass went further: the real
  `FundamentalAnalystAgent`, real `RetrievalEngineService`, and real
  Postgres data for TCS were run end-to-end with only the LLM HTTP call
  itself swapped for a stub returning canned JSON. This confirmed, against
  genuine evidence identities pulled from the real database: a
  hallucinated citation index is correctly dropped (not silently kept),
  a valid citation correctly resolves to a real evidence row's database
  identity, the investment-advice-language filter correctly rejects a
  response containing "Investors should buy this stock immediately," and
  a response that doesn't match `LLMFundamentalOutput`'s schema is
  correctly rejected with `LLMResponseParsingError`. What remains
  genuinely unverified is only the actual OpenAI HTTP round trip itself
  (request formatting, real response parsing, real model behavior/
  quality) — covered by `test_llm_provider.py`'s mocked-response tests
  only. The user explicitly chose, a second time (after the same choice
  at v0.7/v0.8), to document this rather than supply a key. **Whoever
  first configures a real `OPENAI_API_KEY` should do one live
  `POST /agents/fundamental/{symbol}` pass against a company with real
  financial statement data before fully trusting this path in
  production** — this sandbox's TCS company has never had
  `sync_company_financials` run against it (see the `retrieval_engine`
  entry above), so even the "sufficient evidence" code path itself has
  only ever been exercised against seeded test data, not real financials.
- **The Fundamental Analyst's "insufficient evidence" short-circuit is,
  as of this writing, the *only* code path this sandbox's real data can
  exercise without any stubbing at all** — TCS has zero synced financial
  statements (see above), so a real `POST /agents/fundamental/TCS` call
  genuinely takes the no-LLM-call, deterministic-floor path in
  production today, not just in tests. This was confirmed live during
  v0.9's own E2E pass (§5/§11) and is not a bug — it is the correct,
  intended behavior for a company with no fundamentals evidence — but it
  means the "happy path" (real evidence, real LLM reasoning) has only
  ever been exercised via seeded/stubbed data, never fully end-to-end
  against this sandbox's actual persisted state.
- **No numeric cross-check against `financials` data** — an LLM-stated
  figure (e.g. "revenue grew 12%") is not compared against the actual
  value already sitting in `FinancialRatio`/`ProfitAndLoss` rows.
  Deliberately deferred out of v0.9's scope (§12 item 11,
  `FUNDAMENTAL_ANALYST_DESIGN.md` §9 point 6) — the strongest single
  hallucination guard proposed in that design doc, and flagged there as
  the module's most consequential known gap at launch.
- **No result caching for `ai_agents`** — every
  `POST /agents/fundamental/{symbol}` re-runs the full pipeline including
  the (paid) LLM call, even if the underlying evidence hasn't changed
  since the last run. Unlike `KnowledgeEmbedding`'s `content_checksum`
  guard (§4 point 5), `AgentFinding` has no equivalent skip mechanism yet
  — see §12 item 12 for why this wasn't built without real cost data to
  justify the design.
- **`ai_agents`'s investment-advice-language filter is pattern-based, not
  exhaustive** — a fixed set of word-boundary regexes
  (`agents/fundamental/validation.py`'s `_ADVICE_PATTERNS`) catches the
  common buy/sell/hold/price-target phrasings, but a sufficiently
  differently-worded piece of advice language could in principle slip
  through undetected. This is a known, accepted limitation of a
  deterministic keyword approach (documented in
  `FUNDAMENTAL_ANALYST_DESIGN.md` §9 as a defense-in-depth layer, not a
  guaranteed-complete one) — not a bug to silently "fix" by expanding the
  pattern list without discussing whether a more robust approach (e.g. a
  second, narrowly-scoped classification pass) is warranted.
- **Eight of the nine specialist agents named in `agents/base.py`'s
  docstring remain unimplemented**, and `InvestmentCommitteeOrchestrator`
  remains a 100% placeholder (`POST /reports` still always `501`s) — v0.9
  built exactly one specialist agent end-to-end, not the whole
  multi-agent system. See §12 item 1.

---

## 15. How a New Claude Conversation Should Continue This Project

1. **Read this file first, in full, before touching anything.**
2. **Do not redesign the architecture.** Every version so far has been
   built under an explicit "architecture is frozen, reuse every existing
   pattern exactly" constraint from the user, and it has held for
   `v0.1` → `v0.9` without exception — including v0.7, v0.8, and v0.9
   themselves, which each added a genuinely new capability
   (embeddings/vector search; hybrid ranked retrieval; the first real LLM
   reasoning) but did so *inside* the existing module shape (§3) and every
   existing convention (§6–§10), not by inventing new ones — v0.9 in
   particular was implemented from a full technical design document
   (`FUNDAMENTAL_ANALYST_DESIGN.md`) reviewed and confirmed with the user
   before any code was written, the same "architecture review first"
   rhythm point 3 below describes. Assume the same constraint applies
   until told otherwise.
3. **When asked to plan/review before building**, do exactly that — no
   code, no file writes — and end with a concrete proposal, not just
   options. This project's actual working rhythm has been:
   architecture-review request → this-style report → user says "yes,
   that's correct, implement it" (sometimes with specific amendments) →
   full implementation → self-driven production code review →
   Ruff/mypy/pytest → live end-to-end verification with a real company
   against a real Postgres/Celery/Redis stack → commit → push to `main`.
4. **For a new domain module**, copy the exact shape in §3/§6/§7/§8: a
   `providers/` package with `base.py`/`exceptions.py`/`factory.py`/one
   concrete provider, `normalization.py`, `validation.py`,
   `repository.py`, `service.py`, `schemas.py`, `router.py`, an Alembic
   migration numbered one past the current highest, a Celery task added
   to the *existing* `ingestion/tasks.py` (never a new tasks file), a
   `tests/<module>/` directory mirroring the src layout, and a one-line
   addition to `backend/tests/conftest.py` importing the new
   `models.py`.
5. **If the new module needs to appear in the Research Dossier**, follow
   §10's recipe exactly — add one `SOURCE_TYPE_*` constant +
   `Literal` value, nothing else in `research/`.
6. **Before declaring anything done**, actually run it: `ruff check .`,
   `ruff format --check .`, `mypy src`, `pytest` (with a real Postgres —
   note in output whether tests ran or skipped), and where feasible, a
   live end-to-end pass through the actual FastAPI + Celery + Postgres
   stack against a real company symbol, not just mocked unit tests. This
   project's history shows real, production-relevant bugs (NaN handling,
   the Celery event-loop bug, a missing dependency, a misleading route
   shape, a missing API field) were caught specifically by this live
   verification step and would **not** have been caught by unit tests
   alone. Do not skip it.
7. **Be honest about data-source limitations** in docstrings and to the
   user, the way every provider in this codebase already is (§8) — this
   project has consistently valued disclosed, deterministic
   approximations over silently fabricated or misleadingly-labeled data.
8. **Only commit/push when explicitly asked**, using the exact commit
   message given if one is given, and only to `main` (there is no
   established branching workflow in this project — every version has
   landed as a direct commit to `main`).

---

## 16. Current REST API Surface

Every route below is mounted under `/api/v1` (see `api/v1/router.py`).
Grouped by module, in the order they were built. `POST .../sync/...` and
`.../generate/...` routes always return `202` with `{symbol, status:
"queued", task_id}` and enqueue a Celery task — they never do the work
inline.

**Health / meta**
- `GET /health` — liveness + downstream dependency checks (Postgres,
  Redis), never raises, reports `"degraded"` in the body instead.
- `GET /version` — app name/version/environment from settings.

**`companies`** (`/companies`)
- `GET /companies?limit=&offset=` — list active companies.
- `GET /companies/{symbol}`

**`market_data`** (`/market`)
- `POST /market/sync/{symbol}`
- `GET /market/history/{symbol}?start=&end=&limit=`

**`financials`** (`/financials`)
- `POST /financials/sync/{symbol}`
- `GET /financials/{symbol}` — overview (latest annual + latest quarterly).
- `GET /financials/{symbol}/annual?limit=`
- `GET /financials/{symbol}/quarterly?limit=`

**`corporate_filings`** (`/filings`)
- `POST /filings/sync/{symbol}`
- `GET /filings/{symbol}?limit=&offset=`
- `GET /filings/{symbol}/annual?limit=`
- `GET /filings/{symbol}/quarterly?limit=`
- `GET /filings/{symbol}/category/{category}?limit=`
- `GET /filings/{symbol}/history?limit=&offset=` — `FilingVersion` audit trail.

**`document_intelligence`** (`/document-intelligence`)
- `POST /document-intelligence/extract/{filing_version_id}`
- `GET /document-intelligence/filing-versions/{filing_version_id}` — full
  detail, including `extracted_text` and `sections`.
- `GET /document-intelligence/{symbol}?limit=&offset=` — lightweight list
  (omits `extracted_text`/`sections`).

**`news_intelligence`** (`/news`)
- `POST /news/sync/{symbol}`
- `GET /news/{symbol}?limit=&offset=`
- `GET /news/{symbol}/category/{category}?limit=`

**`technical_intelligence`** (`/technical`) — added v0.6
- `POST /technical/generate/{symbol}`
- `GET /technical/{symbol}/latest` — one row per `indicator_name`, most
  recent `trading_date` each has.
- `GET /technical/{symbol}/history?limit=&offset=` — all indicators, all
  dates, newest first.
- `GET /technical/{symbol}/indicator/{indicator_name}?limit=&offset=` —
  one indicator's full history (e.g. `rsi_14`).

**`knowledge_layer`** (`/knowledge`) — added v0.7
- `POST /knowledge/generate/{symbol}` — gathers, checksums, and embeds a
  company's textual knowledge (skipping unchanged content); standard
  `202` + queued-task response.
- `GET /knowledge/{symbol}?limit=&offset=` — stored embedding rows'
  metadata (`source_type`, `source_table`, `source_id`, `title`,
  `content_text`, `embedding_model`), newest-updated first. The raw
  vector itself is never returned over REST.
- `GET /knowledge/{symbol}/search?query=&limit=` — semantic similarity
  search scoped to one company. This is a `GET`, not a `.../sync/` or
  `.../generate/` route, and it makes a live external embedding API call
  inline (to embed `query`) rather than queuing Celery work — a search
  query needs a fresh embedding to compare against; there's no "do it
  later" version of that. Returns cosine similarity scores (1 = identical
  direction, not a percentage). `retrieval_engine`'s endpoints below make
  the same kind of live call for the same reason.

**`retrieval_engine`** (`/retrieval`) — added v0.8; read-only, no
Celery task exists for this module (§9)
- `GET /retrieval/{symbol}/evidence?query=&limit=` — hybrid ranked
  evidence: semantic hits (via `knowledge_layer`) plus structured SQL
  facts (financials, technical indicators, filings, document sections,
  news), deduplicated and scored onto one 0..1 `relevance_score` scale.
  `query` is required — see §7 for why. Degrades gracefully to
  structured-only results if the embedding provider fails (§7/§14).
- `GET /retrieval/{symbol}/context?query=&limit=` — the same evidence
  wrapped in a `ContextPackage`: adds `generated_at` and a deterministic,
  citation-annotated `context_text` block suitable as an LLM prompt's
  evidence section (built by formatting already-scored evidence, not by
  summarizing it).
- `GET /retrieval/{symbol}/inspect?query=&limit=` — diagnostics for a
  *live* retrieval call: per-source-type fetch counts before dedup,
  total fetched, total after dedup, total returned. Exists in place of a
  persisted retrieval history (§13 point 1b) — there is nothing to look
  back on, only a live call to inspect.

**`research`** (`/research`) — read-only; never triggers a sync itself
- `GET /research/{symbol}` — dossier overview: latest version + snapshot,
  recent timeline, evidence summary (`{source_type, record_count}` per
  `SOURCE_TYPE_*`).
- `GET /research/{symbol}/history?limit=&offset=`
- `GET /research/{symbol}/latest`

**`portfolios`** (`/portfolios`) — every route requires
`get_current_user` (placeholder auth, §13/§14)
- `GET /portfolios`
- `POST /portfolios`

**`ai_agents`** — two route groups, added incrementally
- `POST /reports` — orchestrator job API, still placeholder-only: always
  ends in a `501` `NotImplementedYetError` once
  `InvestmentCommitteeOrchestrator.request_analysis` runs; kept mounted so
  the route shape is already correct for when it's implemented.
- `POST /agents/fundamental/{symbol}` — added v0.9. Runs the Fundamental
  Analyst for a company: retrieves ranked evidence via
  `RetrievalEngineService`, calls the LLM behind the `LLMProvider`
  abstraction, validates/guards the structured output, persists the
  result to `agent_findings`, and links it into the Research Dossier.
  Standard `202` + `{symbol, status: "queued", task_id}` response,
  following every other `.../generate/` route's convention — an LLM call
  is slow and costs real money, exactly the profile that convention
  exists for.
- `GET /agents/fundamental/{symbol}` — added v0.9. Reads the most
  recently persisted `AgentFinding` for that company (`404` if none
  exists yet — the response message includes the exact `POST` to run).
  `result_json` is the full `FundamentalAnalysisResult` payload
  (summary, strengths, concerns, resolved citations, confidence score,
  evidence sufficiency, caveats) passed through as-is.

---

## 17. Version 0.10 — Specification Status

**No Version 0.10 specification has been given by the user as of this
document's last update.** Do not infer one and do not start implementing
anything under a "v0.10" label without first getting an explicit,
detailed spec from the user, the same way v0.3 through v0.9 each began
with one (see §15 point 3 for the established rhythm: architecture review
first, user confirms scope, then implement).

§12 (Current Roadmap) lists the candidate next-step directions already
identified from what v0.4 through v0.9 were each explicitly built to
enable — more `ai_agents` specialist agents and/or the Investment
Committee orchestrator itself (§12 item 1), a real filings-discovery
provider, a second news provider, real authentication, portfolio
analytics, frontend wiring, raw document storage, a pgvector ANN index,
revisiting `retrieval_engine`'s scoring formula now that a real consumer
exists, a numeric cross-check for the Fundamental Analyst, findings
caching, and auto-chaining `generate_fundamental_analysis` — roughly in
dependency order. These are **candidates the user has not yet chosen
from or approved**, not a queued backlog to work through automatically.
When a new conversation picks this up, the first step is asking the user
which of these (or something else entirely) Version 0.10 should be, not
assuming §12's ordering is a decision.

If Version 0.10 turns out to be another `ai_agents` specialist agent:
read `ai_agents/agents/fundamental/` in full first — it is the intended
template (§12 item 1) — and read §13 points 1 and 1c carefully;
`FundamentalAnalystAgent`'s guardrails (citation enforcement, the
investment-advice filter, the two-part confidence score, the fail-closed-
not-degrade-gracefully asymmetry with `retrieval_engine`) are frozen
decisions for *that* agent, not necessarily the only valid design for a
different agent's domain (e.g. a Technical Analyst's "is there enough
evidence" question looks nothing like "is there a financial statement"),
but the *pattern* of deterministic, non-LLM guardrails wrapping every LLM
call should be treated as the house style going forward, not something
each new agent reinvents from scratch. If Version 0.10 turns out to be
the Investment Committee orchestrator itself: this document should not be
read as having pre-approved any particular orchestrator design — conflict
detection, weighted scoring, a Findings Store schema, and the
synthesis/Compliance-Agent pass all remain fully unscoped (see §12 item 1
and `FUNDAMENTAL_ANALYST_DESIGN.md` §13) and need their own explicit spec
and architecture-review pass, the same as every version before it.

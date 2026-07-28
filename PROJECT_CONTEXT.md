# PROJECT_CONTEXT.md

**Purpose of this document:** permanent project memory. A brand-new Claude
conversation (or a new human engineer) should be able to read this file and
continue development with zero loss of context. Written as an onboarding
document for a Senior Staff Engineer joining the project.

Last updated: after v0.5 (News Intelligence Engine).

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
- No AI/LLM/embeddings/vector DB/knowledge graph anywhere in the currently
  built modules (v0.1–v0.5). All ingestion, normalization, validation, and
  categorization is deterministic (fixed lookup tables, regex/string
  heuristics, arithmetic). The `ai_agents` module is a fully-stubbed
  placeholder reserved for this later (see §12).
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
│   ├── alembic/versions/        # 0001..0005, see §4
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
│   │   ├── ai_agents/           # Investment Committee -- fully stubbed, no logic
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
`corporate_filings`, `document_intelligence`, `news_intelligence`) has the
**identical internal shape**:

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

### Dependencies (`backend/pyproject.toml`)

Runtime: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `asyncpg`,
`psycopg2-binary`, `pydantic`, `pydantic-settings`, `redis`, `celery`,
`python-dotenv`, `httpx`, `yfinance`, `pandas`, `lxml`, `pypdf`,
`beautifulsoup4`. Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`,
`pre-commit`. No lock file — `uv sync` resolves fresh from `pyproject.toml`
each time (CI does the same).

---

## 4. Database Schema Summary

Single Postgres database, single `Base`. Alembic migrations `0001`–`0006`,
applied in order, no branches:

| Migration | Tables |
|---|---|
| `0001_initial_schema` | `exchanges`, `companies`, `historical_ohlcv`, `corporate_actions`, `portfolios`, `holdings` |
| `0002_research_dossier` | `company_research_dossiers`, `research_versions`, `research_snapshots`, `research_timeline`, `research_sources` |
| `0003_financial_statements` | `financial_statements`, `balance_sheets`, `profit_and_loss_statements`, `cash_flow_statements`, `quarterly_results`, `financial_ratios` |
| `0004_corporate_filings` | `filing_categories`, `filing_sources`, `corporate_filings`, `filing_versions` |
| `0005_document_intelligence` | `document_extractions`, `document_sections` |
| `0006_news_intelligence` | `news_articles` |

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
```

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
  a DB. As of v0.5: **313 tests**, all passing with a live Postgres, Ruff
  and mypy both clean across the whole `src/` tree.

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
  boundary should ever need to change.
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
  only `DuplicateExtractionError` from `document_intelligence`) are caught
  **before** the generic `except Exception` handler and re-raised without
  `self.retry(...)` — logged and left failed, not retried. Every other
  exception (including validation failures like `InvalidFilingDataError`)
  is retried blindly up to 3 times, even though a permanent validation
  failure will never succeed on retry — this is the established, if
  imperfect, behavior everywhere in this codebase; don't "fix" it locally
  in one module without discussing it, since consistency has been treated
  as more important than local optimality here.
- **Auto-chaining convention**: a successful sync task may trigger the
  next task in the pipeline via `.delay(...)` at the end of its
  celery-task wrapper (not the service). Established chain today:
  `sync_company_market_data` → (always) `refresh_company_dossier`;
  `sync_company_filings` → (only for filing versions the sync *just
  created*, and only for extractable filing types) `extract_filing_document`
  per version. `sync_company_financials` and `sync_company_news` do **not**
  currently auto-chain into anything -- there is no downstream module that
  consumes financials or news yet.
- Current task inventory (`ingestion.*`): `refresh_company_dossier`,
  `sync_company_market_data`, `sync_company_financials`,
  `sync_company_filings`, `extract_filing_document`, `sync_company_news`.
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
module plugs into, and it has been extended **three times** now (v0.3,
v0.4, v0.5) using the identical recipe, with **zero changes** to
`ResearchPipelineService`'s or `ResearchDossierRepository`'s existing write
logic any time:

```python
SOURCE_TYPE_MARKET_DATA = "market_data"
SOURCE_TYPE_FINANCIAL_DATA = "financial_data"        # added v0.3
SOURCE_TYPE_CORPORATE_ACTION = "corporate_action"
SOURCE_TYPE_CORPORATE_FILING = "corporate_filing"     # added v0.3
SOURCE_TYPE_DOCUMENT_EXTRACTION = "document_extraction"  # added v0.4
SOURCE_TYPE_NEWS = "news"                             # populated v0.5
SOURCE_TYPE_TECHNICAL_INDICATOR = "technical_indicator"  # reserved, unused
```

`SOURCE_TYPE_NEWS` had already existed as a reserved-but-unused constant
since Sprint 3 (see the module's own "extend the catalog, not the schema"
docstring, written in anticipation of exactly this) -- v0.5 is the first
version to actually populate it, which meant **zero changes** to
`research/models.py` or `research/schemas.py` were needed at all, only a
plain `from nivesh.research.models import SOURCE_TYPE_NEWS` in
`news_intelligence/service.py`.

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

---

## 11. Completed Versions (v0.1 – v0.5)

| Version | Delivered | Key modules/tables |
|---|---|---|
| **v0.1 (scaffold)** | Initial commit: FastAPI/Next.js/Docker scaffold, `companies`, `market_data` (yfinance dev provider), `portfolios` (CRUD only), `ai_agents` (fully stubbed), placeholder auth. | `exchanges`, `companies`, `historical_ohlcv`, `corporate_actions`, `portfolios`, `holdings` |
| **Sprint 3 (research)** | Deterministic Research Dossier pipeline: aggregates already-persisted market data into versioned, immutable snapshots. No AI. | `company_research_dossiers`, `research_versions`, `research_snapshots`, `research_timeline`, `research_sources` |
| **v0.3(a) — Sprint 4: Financial Statements Engine** | Ingests/validates/versions/exposes financial statements (balance sheet, P&L, cash flow, quarterly results, ratios computed deterministically). yfinance dev provider. Fixed 2 pre-existing mypy errors in `research` while there. | `financial_statements` + 5 child tables |
| **v0.3(b) — Sprint 5: Corporate Filings Metadata Engine** | Structured catalog of filing *metadata only* (no PDF parsing, no downloading). `CorporateFiling` (current state) + `FilingVersion` (immutable history) pattern. yfinance-derived dev provider (see §8 for its real limitations). During E2E verification of this version, **3 real pre-existing platform bugs were found and fixed**: (1) `market_data/validation.py` crashed on NaN prices instead of filtering them (`decimal.InvalidOperation`); (2) the Celery event-loop/`engine.dispose()` bug (§9); (3) `lxml` was a transitively-relied-on but undeclared dependency. | `filing_categories`, `filing_sources`, `corporate_filings`, `filing_versions` |
| **v0.4 — Document Intelligence Engine** | Deterministic text extraction from filing documents (PDF via `pypdf`, HTML via `bs4`+`lxml` — see §8 for why both), heading/section detection via string heuristics (numbering, ALL CAPS, Title Case — never AI), stored as flat text + structured sections in Postgres. Keyed 1:1 off the immutable `FilingVersion` identity. Auto-triggered off newly-synced filings. During build/review, **3 gaps were found and fixed before release**: (1) the provider was PDF-only despite the real dev-provider data being HTML — added format detection; (2) the API router disambiguated symbol-vs-UUID by runtime type-sniffing on one shared route, inconsistent with every other router's literal-path-segment convention — split into two explicit routes; (3) `FilingVersionRead` didn't expose `id`, making the new endpoints undiscoverable via the API — added it. | `document_extractions`, `document_sections` |
| **v0.5 — News Intelligence Engine** | Per-company news article catalog, ingested via a yfinance-backed dev provider (`Ticker.news`, real publications like Reuters/Bloomberg/Verdict). No versioning (a news article is immutable once published — same "no versioning needed" precedent as `document_intelligence`, see §4); dedup and idempotent re-sync via a `checksum` unique constraint. **Deduplication is scoped per-provider only by explicit user decision** during v0.5 planning: `checksum = sha256(company_id \| provider \| canonicalized_url)`, so the same URL from two different providers is stored as two separate articles rather than merged — true cross-provider identity resolution (recognizing the same real-world story reported under different URLs) is deferred to a future version once a second real provider exists to design that logic against real data. `category` is assigned via a small fixed keyword → category lookup applied to the title (`earnings`/`corporate_action`/`regulatory`/`markets`/`general`) — a deterministic string-heuristic classification, the same "not AI" spirit as `document_intelligence`'s heading detection, not a learned or LLM-based classifier. `SOURCE_TYPE_NEWS` had been reserved-but-unused in `research/models.py` since Sprint 3 specifically for this — v0.5 required **zero changes** to `research/models.py` or `research/schemas.py`. One real bug found during E2E verification: the local Windows dev Postgres cluster used for prior sessions' verification had been `initdb`'d with `WIN1252` server encoding (inherited from the OS locale) instead of UTF8, so it rejected real news text containing non-Latin1 Unicode (smart quotes, zero-width joiners) with `UntranslatableCharacterError`. Confirmed this is a **local sandbox artifact, not an application bug** (the project's `docker-compose.yml` Postgres image, `postgres:16-alpine`, defaults to UTF8) by recreating a UTF8-encoded database in the same cluster and re-verifying successfully — no application code changed for this. | `news_articles` |

**Test count as of v0.5: 313 passing** (`pytest`, real Postgres). Ruff and
mypy both clean across the whole `src/` tree.

Commits (chronological, all on `main`):
`6d5e038` init → `9c8ff36` gitignore → `f616f25` Sprint 4 → `fe5a0e4` ruff
fixes → `d308b17` mypy fixes → `53b1e66` feat(v0.3) corporate filings →
`d3f691c` feat(v0.4) document intelligence → (v0.5 news intelligence, see
git log for the current hash).

---

## 12. Current Roadmap (v0.6 onwards)

Nothing beyond v0.5 has been scoped or approved yet. Do not start
implementing v0.6 without an explicit spec from the user — this project's
working pattern has consistently been: architecture review first (no code)
→ user confirms scope → implement → self-review → verify → commit/push.

**What v0.4 and v0.5 were explicitly building toward**: document
extractions and news articles exist so a *future* version can consume
them. Natural, foreshadowed next steps, roughly in dependency order:

1. **A real filings-discovery provider** for `corporate_filings` (NSE/BSE
   announcements API or a commercial vendor) that supplies genuine
   document deep-links — this would make `document_intelligence`'s PDF
   path the common case instead of the fallback, with zero changes needed
   to `document_intelligence` itself (the whole point of the provider
   abstraction).
2. **A second real news provider** for `news_intelligence` (Reuters,
   Economic Times, Moneycontrol, Google News, etc.) — needed before true
   cross-provider duplicate-article identity resolution can be designed
   and validated against real data (see §11's v0.5 entry and §14 for why
   this was deliberately deferred rather than guessed at speculatively).
3. **The `ai_agents` / Investment Committee layer** — currently 100%
   placeholder (`InvestmentCommitteeOrchestrator.request_analysis` always
   raises `NotImplementedYetError`; `BaseAgent`/`AgentContext`/
   `AgentFinding` define a contract with no implementations). This is
   where AI/LLM reasoning is *supposed* to live, per the external
   architecture docs' "Findings Store" / "Knowledge Layer" / "Evidence
   Graph" concepts — none of which exist in this codebase yet. Building
   this is a materially different kind of work (the first version to
   actually use AI) and should not be started casually. News sentiment
   analysis / AI summarization of articles belongs here, not in
   `news_intelligence` — explicitly out of scope for v0.5 per the user's
   instructions.
4. **Real authentication** (`core/security.py` is an explicit,
   documented placeholder — swap for Clerk/Auth.js or similar).
5. **Portfolio analytics** (`portfolios/service.py`'s docstring: "Portfolio
   analytics... are produced by the Portfolio Analysis Agent, not this
   service" — i.e. this is blocked on #3).
6. **Frontend wiring** — the Next.js app currently has placeholder pages
   with "No data yet" copy; `lib/api-client.ts` exists but nothing calls
   the real backend endpoints yet.
7. **Raw document storage** — explicitly postponed in v0.4 (see §13). If
   ever revisited, requires a real infrastructure decision (S3/MinIO) that
   doesn't exist in this stack today.

---

## 13. Architectural Decisions That Must Never Change (without an explicit,
deliberate conversation with the user first)

1. **Determinism until `ai_agents` is explicitly greenlit.** No AI, no
   LLM calls, no embeddings, no vector database, no semantic search, no
   sentiment analysis, no knowledge graph anywhere outside `ai_agents`.
   This has been a hard constraint on every version so far, restated
   explicitly by the user for both v0.4 and v0.5 (v0.5's restatement
   specifically named AI summarization, sentiment analysis, and semantic
   search as excluded from `news_intelligence`).
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

---

## 15. How a New Claude Conversation Should Continue This Project

1. **Read this file first, in full, before touching anything.**
2. **Do not redesign the architecture.** Every version so far has been
   built under an explicit "architecture is frozen, reuse every existing
   pattern exactly" constraint from the user, and it has held for
   `v0.1` → `v0.5` without exception. Assume the same constraint applies
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

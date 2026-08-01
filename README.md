# Nivesh AI

Institutional-grade AI investment research platform for Indian equities. This is a
research and analysis platform, not a trading platform -- it never places, modifies,
or executes trades. Users act on its research manually, on their own brokerage.

## Project Setup

Prerequisites: Docker and Docker Compose, Python 3.12, [uv](https://github.com/astral-sh/uv),
Node.js 20+.

```bash
cp .env.example .env
```

Review `.env` and adjust values if needed -- the defaults work out of the box with
Docker Compose.

### Backend (local, without Docker)

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn nivesh.main:app --reload
```

### Frontend (local, without Docker)

```bash
cd frontend
npm install
npm run dev
```

#### Frontend development workflow

`next dev` and `next build`/`next start` write incompatible artifacts into the
same `frontend/.next` directory. Running a production build or `next start`
locally (e.g. to sanity-check the standalone server) and then going back to
`next dev` on top of that same `.next` folder can corrupt the dev cache --
symptoms are things like pages rendering unstyled (compiled CSS 404s
intermittently) or console errors like `Could not find module ... in the
React Client Manifest` / `__webpack_modules__ is not a function`. This is a
real incident this project hit, not a hypothetical.

- **Normal day-to-day dev**: just `npm run dev`. `next.config.ts` only enables
  `output: "standalone"` during the production build phase specifically so it
  can't affect `next dev`.
- **If you need to test a local production build** (`npm run build` /
  `npm start`), do it in a separate pass, then run `npm run clean` before
  switching back to `npm run dev`.
- **If dev ever renders unstyled or throws bundler errors like the ones
  above**, stop the dev server, run `npm run clean` (deletes `.next`), and
  restart `npm run dev`.
- Docker builds (`docker compose up --build`) are unaffected either way --
  each service's Dockerfile builds in a clean container from a `.dockerignore`d
  context, never reusing a host `.next`/`node_modules`.

## How to Run

Run the full stack (Postgres, Redis, backend, Celery worker, frontend) with Docker Compose:

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs` in non-production environments)
- Frontend: http://localhost:3000
- Health check: http://localhost:8000/api/v1/health

Or use the helper script, which also bootstraps `.env` on first run:

```bash
./scripts/dev.sh
```

## Folder Overview

```
backend/     FastAPI application (API, domain modules, AI agent scaffolding, Celery tasks)
frontend/    Next.js application (App Router, TypeScript, Tailwind CSS)
docker/      Dockerfiles for backend, worker, and frontend
infra/       Deployment-environment infrastructure (reverse proxy, future IaC)
scripts/     Development helper scripts (dev, lint, test, migrate)
tests/       End-to-end tests (Playwright), separate from backend/tests (unit tests)
.github/     CI workflows
docs/        Pointer to the architecture and database design documentation
```

## Development Commands

| Command | Description |
|---|---|
| `./scripts/dev.sh` | Start the full stack via Docker Compose |
| `./scripts/lint.sh` | Run Ruff, mypy, ESLint, and tsc across both apps |
| `./scripts/test.sh` | Run backend pytest suite |
| `./scripts/test.sh --e2e` | Run backend tests plus Playwright end-to-end tests |
| `./scripts/migrate.sh` | Apply database migrations |
| `cd backend && uv run pytest` | Run backend tests directly |
| `cd backend && uv run ruff format .` | Format backend code |
| `cd frontend && npm run build` | Production build of the frontend |
| `cd frontend && npm run clean` | Remove `frontend/.next` (see Frontend development workflow above) |
| `pre-commit install` | Enable pre-commit hooks (Ruff, mypy, basic hygiene checks) |

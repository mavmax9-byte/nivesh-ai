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
| `pre-commit install` | Enable pre-commit hooks (Ruff, mypy, basic hygiene checks) |

"""Market Universe routes.

Ops-facing endpoints for managing the tracked company universe (v1.4) --
no frontend page consumes these directly (`portfolio_planner`'s existing
`/planner` UI already renders whatever multi-company universe results
from this pipeline, unchanged, see PROJECT_CONTEXT.md §3). Seeding and
screening are synchronous, cheap DB operations; per-constituent ingestion
and any resulting Investment Committee runs are enqueued as Celery tasks,
the same async-job shape every other expensive operation in this
codebase uses.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.core.exceptions import NotFoundError
from nivesh.dependencies import get_db
from nivesh.ingestion.tasks import screen_universe, sync_universe_constituent
from nivesh.market_universe.constituents import INDEX_NIFTY50, NIFTY_50_SYMBOLS
from nivesh.market_universe.repository import UniverseConstituentRepository
from nivesh.market_universe.schemas import (
    ConstituentRead,
    ScreenRequest,
    ScreenResponse,
    SeedResponse,
    SyncRequest,
    SyncResponse,
)
from nivesh.market_universe.service import DEFAULT_SCREEN_TOP_N

router = APIRouter(prefix="/universe", tags=["market-universe"])


@router.post("/seed", response_model=SeedResponse)
async def seed_universe(db: AsyncSession = Depends(get_db)) -> SeedResponse:
    """Idempotent -- creates a tracked row for every Nifty 50 symbol not
    already tracked; existing rows (and their ingestion progress) are
    left untouched."""
    repo = UniverseConstituentRepository(db)
    seeded = await repo.seed(INDEX_NIFTY50, NIFTY_50_SYMBOLS)
    total = len(await repo.list_by_index(INDEX_NIFTY50))
    return SeedResponse(index_name=INDEX_NIFTY50, seeded=seeded, total_tracked=total)


@router.post("/sync", response_model=SyncResponse, status_code=202)
async def sync_universe(
    payload: SyncRequest,
    db: AsyncSession = Depends(get_db),
) -> SyncResponse:
    """Enqueues `sync_universe_constituent` for the requested symbols (or
    every currently `pending`/`failed` tracked constituent if none are
    given) -- one Celery task per company, each independently retried on
    transient failure and terminally recorded on a real, non-transient
    one (see the task's own docstring)."""
    repo = UniverseConstituentRepository(db)
    if payload.symbols:
        targets = [s.upper() for s in payload.symbols]
    else:
        pending = await repo.list_by_index(INDEX_NIFTY50, statuses={"pending", "failed"})
        targets = [c.symbol for c in pending]

    for symbol in targets:
        sync_universe_constituent.delay(INDEX_NIFTY50, symbol)

    return SyncResponse(index_name=INDEX_NIFTY50, queued=targets)


@router.post("/screen", response_model=ScreenResponse, status_code=202)
async def screen_universe_route(payload: ScreenRequest) -> ScreenResponse:
    """Screening (a bulk scan/score/rank across the whole universe) and
    any resulting Investment Committee runs both happen inside one
    Celery task (`screen_universe`, `ingestion/tasks.py`) -- this
    endpoint only confirms the request was queued; poll `GET /universe`
    afterward for `is_screened_in`/`screening_score` once it completes."""
    top_n = payload.top_n or DEFAULT_SCREEN_TOP_N
    screen_universe.delay(INDEX_NIFTY50, top_n)
    return ScreenResponse(index_name=INDEX_NIFTY50, top_n=top_n)


@router.get("", response_model=list[ConstituentRead])
async def list_universe(
    index_name: str = INDEX_NIFTY50,
    db: AsyncSession = Depends(get_db),
) -> list[ConstituentRead]:
    repo = UniverseConstituentRepository(db)
    constituents = await repo.list_by_index(index_name)
    return [ConstituentRead.model_validate(c) for c in constituents]


@router.get("/{symbol}", response_model=ConstituentRead)
async def get_constituent(
    symbol: str,
    index_name: str = INDEX_NIFTY50,
    db: AsyncSession = Depends(get_db),
) -> ConstituentRead:
    repo = UniverseConstituentRepository(db)
    constituent = await repo.get_by_symbol(index_name, symbol)
    if constituent is None:
        raise NotFoundError(f"No universe constituent found for symbol '{symbol}'")
    return ConstituentRead.model_validate(constituent)

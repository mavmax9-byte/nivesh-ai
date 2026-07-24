"""Shared pytest fixtures."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import every model module so Base.metadata is fully populated before
# create_all/drop_all run in the db_session fixture below.
from nivesh.companies import models as _companies_models  # noqa: F401
from nivesh.config import get_settings
from nivesh.core.db import Base
from nivesh.main import create_app
from nivesh.market_data import models as _market_data_models  # noqa: F401
from nivesh.portfolios import models as _portfolios_models  # noqa: F401
from nivesh.research import models as _research_models  # noqa: F401


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Real PostgreSQL session against TEST_DATABASE_URL.

    Used by repository tests that exercise actual Postgres-specific
    behavior (ON CONFLICT upsert) that cannot be meaningfully faked with an
    in-memory database. Skips cleanly if the test database is unreachable,
    so the rest of the suite stays runnable without Postgres installed.
    """
    settings = get_settings()
    engine = create_async_engine(settings.TEST_DATABASE_URL)

    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip(
            "TEST_DATABASE_URL is not reachable -- start it with "
            "`docker compose up -d postgres` and create the nivesh_test database."
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

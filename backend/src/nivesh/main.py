"""Application entrypoint -- FastAPI app factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from nivesh.api.v1.router import api_v1_router
from nivesh.config import get_settings
from nivesh.core.exceptions import register_exception_handlers
from nivesh.core.middleware import register_middleware
from nivesh.logging_config import configure_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description="Institutional-grade AI investment research platform for Indian equities. "
        "Research and analysis only -- this platform never executes trades.",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url=None,
    )

    register_middleware(app)
    register_exception_handlers(app)

    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()

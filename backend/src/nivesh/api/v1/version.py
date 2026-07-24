"""Build/version metadata endpoint."""

from fastapi import APIRouter

from nivesh.config import get_settings

router = APIRouter(tags=["version"])


@router.get("/version")
async def get_version() -> dict:
    settings = get_settings()
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }

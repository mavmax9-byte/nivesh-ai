"""Redis client factory.

Reused across caching, the Celery broker/result backend, and (in later
phases) the Research Pipeline event stream -- see docs/db 20 for the
consolidated infra map.
"""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from nivesh.config import get_settings

settings = get_settings()

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding the shared Redis client."""
    yield get_redis_client()

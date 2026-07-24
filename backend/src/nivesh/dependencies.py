"""Shared dependency-injection providers re-exported for convenience.

Domain routers import from here rather than reaching into `core.*` directly,
keeping one stable import surface if the underlying providers move.
"""

from nivesh.core.db import get_db
from nivesh.core.redis_client import get_redis
from nivesh.core.security import CurrentUser, get_current_user

__all__ = ["get_db", "get_redis", "get_current_user", "CurrentUser"]

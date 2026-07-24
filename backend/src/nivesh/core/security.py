"""Authentication placeholder.

Real authentication is delegated to a managed provider (Clerk / Auth.js, per
the approved technology stack) and is not implemented in this scaffold. This
module defines the shape every protected route will depend on so routers can
be wired up now and switched to real verification later without touching
call sites.
"""

from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class CurrentUser:
    id: str
    tenant_id: str


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Placeholder auth dependency.

    TODO: replace with real bearer-token verification against the managed
    auth provider before any endpoint depending on this is exposed publicly.
    """
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header (placeholder auth -- not yet implemented).",
        )
    return CurrentUser(id="00000000-0000-0000-0000-000000000000", tenant_id="dev-tenant")

"""Every authorisation dependency, in one place (P-XCT-05, S7.5, FR-ADR-009/011).

Authorisation is attached ONCE, on a router, as `APIRouter(dependencies=[Depends(...)])`. A handler
contains no role check - if you are about to write `if user.role ...` in a handler, the route is on the
wrong router. The routers and what they carry:

    public        /api, /api/auth (sign-in etc.)     nothing
    session       /api/auth (me)                      current_user
    admin         /api/admin                          require_admin
    reporting     /api/reports                        require_reporting   (manager or admin; GET only)

The role is read from the users row ON EVERY REQUEST, never from the token's `role` claim, so a role
change takes effect on the very next request (S-XCT-10). The token's `pv` must match the row's
password_version, so a password change revokes every older session (P-ACC-05).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import SESSION_COOKIE, ExpiredSession, InvalidSession, decode_session_token
from app.models import users


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    role: str
    password_version: int


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


async def db(request: Request) -> AsyncIterator[AsyncConnection]:
    """One pooled connection for the whole request, shared by every dependency and the handler
    (FastAPI caches a dependency per request). Returned to the pool when the request ends; a
    transaction left open is rolled back by the pool, never committed."""
    async with request.app.state.db_engine.connect() as conn:
        yield conn


async def current_user(
    request: Request,
    conn: AsyncConnection = Depends(db),
    settings: Settings = Depends(get_settings),
    clock: Clock = Depends(get_clock),
) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ApiError(401, "AUTH_REQUIRED")  # P-XCT-05 row 1 - the generic "Sign in to continue."
    # The account surface (/api/auth, EP-ACC-04) speaks P-ACC-05's words for a bad or expired token;
    # every other surface speaks P-XCT-05 row 2's. The two rows publish different sentences for the
    # same condition - a PRD conflict reported by the account lane; each row keeps its own surface.
    account_surface = request.url.path.startswith("/api/auth/")
    try:
        claims = decode_session_token(token, now=clock.now(), settings=settings)
    except ExpiredSession:
        message = "Your session has ended. Sign in to continue." if account_surface else "You were signed out. Sign in again to continue."
        raise ApiError(401, "AUTH_REQUIRED", message) from None  # P-ACC-05 row 3 / P-XCT-05 row 2
    except InvalidSession:
        message = None if account_surface else "You were signed out. Sign in again to continue."
        raise ApiError(401, "AUTH_REQUIRED", message) from None  # P-ACC-05 row 2 / P-XCT-05 row 2
    row = (
        await conn.execute(
            select(users.c.id, users.c.email, users.c.role, users.c.password_version).where(users.c.id == claims["user_id"])
        )
    ).first()
    # End the read's implicit transaction now, so the handler can open its own with `conn.begin()`.
    await conn.rollback()
    if row is None:
        raise ApiError(401, "AUTH_REQUIRED")  # P-ACC-05 row 5
    if row.password_version != claims["pv"]:
        raise ApiError(401, "AUTH_REQUIRED", "Your session has ended because the password was changed. Sign in to continue.")
    return CurrentUser(id=row.id, email=row.email, role=row.role, password_version=row.password_version)


def require_role(*roles: str):
    allowed = frozenset(roles)

    async def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise ApiError(403, "FORBIDDEN")
        return user

    dependency.__name__ = "require_role_" + "_".join(sorted(allowed))
    return dependency


# The two role sets the routers use. Module-level objects, so a handler that also needs the user can
# `Depends(require_admin)` and FastAPI reuses the router's already-resolved result.
require_admin = require_role("admin")
require_reporting = require_role("manager", "admin")

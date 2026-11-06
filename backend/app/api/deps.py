"""Every authorisation dependency, in one place (P-XCT-05, S7.5, FR-ADR-009/011).

Authorisation is attached ONCE, on a router, as `APIRouter(dependencies=[Depends(...)])`. A handler
contains no role check - if you are about to write `if user.role ...` in a handler, the route is on the
wrong router. The routers and what they carry:

    public        /api, /api/auth (sign-in etc.)     nothing
    session       /api/auth (me)                      current_user
    admin         /api/admin                          require_admin
    reporting     /api/reports                        require_reporting, report_scope   (manager or admin; GET only)
    change log    /api/reports/audit                  require_change_log, reports_rate_limit   (admin only)

The role is read from the users row ON EVERY REQUEST, never from the token's `role` claim, so a role
change takes effect on the very next request (S-XCT-10). The token's `pv` must match the row's
password_version, so a password change revokes every older session (P-ACC-05).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.ratelimit import Bucket, enforce
from app.core.security import SESSION_COOKIE, ExpiredSession, InvalidSession, decode_session_token
from app.domain.accounts import Role
from app.models import manager_screen_assignment as msa
from app.models import screen, users


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
    # The reporting surface speaks P-RPT-01 row 4 / P-RPT-02 row 1 for no token AND for an expired one.
    reports_surface = request.url.path.startswith("/api/reports/")
    if not token:
        # P-XCT-05 row 1 - the generic "Sign in to continue." - except on the reporting surface.
        raise ApiError(401, "AUTH_REQUIRED", REPORTS_SIGN_IN if reports_surface else None)
    # The account surface (/api/auth, EP-ACC-04) speaks P-ACC-05's words for a bad or expired token;
    # every other surface speaks P-XCT-05 row 2's. The two rows publish different sentences for the
    # same condition - a PRD conflict reported by the account lane; each row keeps its own surface.
    account_surface = request.url.path.startswith("/api/auth/")
    try:
        claims = decode_session_token(token, now=clock.now(), settings=settings)
    except ExpiredSession:
        message = "Your session has ended. Sign in to continue." if account_surface else "You were signed out. Sign in again to continue."
        raise ApiError(401, "AUTH_REQUIRED", REPORTS_SIGN_IN if reports_surface else message) from None  # P-ACC-05 row 3 / P-XCT-05 row 2
    except InvalidSession:
        message = None if account_surface else "You were signed out. Sign in again to continue."
        message = REPORTS_SIGN_IN if reports_surface else message
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


def require_role(*roles: str, message: str | None = None):
    """`message` is the refusing surface's own 403 sentence; None is the registry default."""
    allowed = frozenset(roles)

    async def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise ApiError(403, "FORBIDDEN", message)
        return user

    dependency.__name__ = "require_role_" + "_".join(sorted(allowed))
    return dependency


# The two role sets the routers use. Module-level objects, so a handler that also needs the user can
# `Depends(require_admin)` and FastAPI reuses the router's already-resolved result.
# P-ADM-18 / P-ADM-01 row 2: the admin surface's refusal. Entity-blind: the same body whether or not the
# addressed film exists, so a refusal never reveals one (S-ADM-01).
require_admin = require_role(
    Role.ADMIN.value, message="This page is for administrators. Your account cannot change films, showtimes, prices or halls.")
require_reporting = require_role(Role.MANAGER.value, Role.ADMIN.value, message="This page is for managers and administrators.")


# ---- the reporting surface (E7, lane p8-reports): rate limit, change-log role, screen scope ----------------------------

REPORTS_SIGN_IN = "Sign in to see the dashboard."  # P-RPT-01 row 4, read by current_user above
# P-RPT-11 rows 1-2: the change log is the admin's alone, and a customer reads the same sentence as a manager.
require_change_log = require_role(Role.ADMIN.value, message="This page is for administrators.")
# P-RPT-12: one per-user bucket shared by every /api/reports endpoint; no per-IP bucket. {span} is ceil(window / capacity).
REPORTS_USER = Bucket("reports:user", "REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE", 60, "Too many requests. Try again in {span}.")
REPORTS_DOWN = "The dashboard cannot be loaded right now. A service it depends on is unreachable."


async def reports_rate_limit(request: Request, user: CurrentUser = Depends(require_reporting)) -> None:
    """Spend one token of the caller's reports bucket. Fails CLOSED: Redis unreachable is 503 (FR-ADR-028)."""
    await enforce(request, [(REPORTS_USER, str(user.id))], REPORTS_DOWN)


@dataclass(frozen=True)
class ReportScope:
    caller_role: str
    all_halls: bool
    readable: tuple[int, ...]  # every hall the caller may read (EP-RPT-03's screens), ascending
    screen_ids: tuple[int, ...]  # the halls THIS response covers: `readable`, or the one hall narrowed to
    # The SQL predicate's list, or None for "no screen predicate at all" (an admin who did not narrow, P-RPT-02).
    filter: tuple[int, ...] | None

    @property
    def empty(self) -> bool:
        return not self.screen_ids


async def report_scope(
    screen_id: int | None = Query(None, gt=0),
    user: CurrentUser = Depends(require_reporting),
    _limited: None = Depends(reports_rate_limit),
    conn: AsyncConnection = Depends(db),
) -> ReportScope:
    """P-RPT-02: the caller's halls, resolved ONCE on the router from the session - never from the request. The
    optional screen_id only narrows: a manager naming a hall they do not hold gets one 403 whether or not it
    exists (no oracle); an admin naming a missing hall gets 404. An out-of-service hall stays readable."""
    admin = user.role == Role.ADMIN.value
    if admin:
        held = (await conn.execute(select(screen.c.id).order_by(screen.c.id))).scalars().all()
    else:
        held = (await conn.execute(select(msa.c.screen_id).where(msa.c.user_id == user.id).order_by(msa.c.screen_id))).scalars().all()
    await conn.rollback()  # end the read's implicit transaction, so the handler can open its own snapshot
    readable = tuple(held)
    if screen_id is None:
        return ReportScope(user.role, admin, readable, readable, None if admin else readable)
    if screen_id not in readable:
        raise ApiError(404, "NOT_FOUND", "That hall does not exist.") if admin else \
            ApiError(403, "FORBIDDEN", "That hall is not assigned to this account.")
    return ReportScope(user.role, admin, readable, (screen_id,), (screen_id,))

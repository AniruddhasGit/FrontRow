"""The caller's own bookings - EP-ACC-07 GET /api/me/bookings, EP-ACC-08 GET /api/me/bookings/{reference}.

/api/me/ means the caller, for every role, with no override (P-ACC-12). The router's dependency resolves the caller
from the session ONCE and leaves it on request.state; no handler takes a user, a user id or a role from anywhere
else, and no handler checks one. Every query filters on that id in the same statement as its lookup.

The list is unlimited - it accepts no identifier, so there is nothing to enumerate. The reference lookup is limited
per user (20/min) and per real client IP (60/min), in Redis, failing closed (EP-ACC-08 rate_limit).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import current_user, db, get_clock, get_settings
from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.ratelimit import Bucket, client_ip, enforce
from app.domain import booking as bk

SIGN_IN = "Sign in to see your bookings."
NOT_YOURS = "No booking with that reference is on your account."
UNAVAILABLE = "Your bookings cannot be loaded right now. Try again shortly."
BAD_GROUP, BAD_PAGE, BAD_PAGE_SIZE = "That is not a valid filter.", "That is not a valid page.", "That is not a valid page size."

LOOKUP_USER = Bucket("lookup:user", "RATE_LIMIT_LOOKUP_USER_PER_MIN", 60, "Too many lookups. Try again in {span}.")
LOOKUP_IP = Bucket("lookup:ip", "RATE_LIMIT_LOOKUP_IP_PER_MIN", 60, "Too many lookups. Try again in {span}.")


async def caller(request: Request, conn: AsyncConnection = Depends(db), settings: Settings = Depends(get_settings),
                 clock: Clock = Depends(get_clock)):
    """The one authorisation dependency of /api/me/: any signed-in account. The caller is left on request.state."""
    try:
        user = await current_user(request, conn, settings, clock)
    except ApiError as exc:
        if exc.status == 401:
            raise ApiError(401, "AUTH_REQUIRED", SIGN_IN) from None
        raise
    request.state.caller = user
    return user


router = APIRouter(prefix="/api/me", dependencies=[Depends(caller)])


def _bounded(raw: str | None, default: int, top: int, message: str, field: str) -> int:
    if raw is None:
        return default
    if not (raw.isascii() and raw.isdigit()) or not 1 <= int(raw) <= top:
        raise ApiError(422, "VALIDATION_FAILED", message, {"field": field})
    return int(raw)


def _down(exc: BaseException) -> bool:
    return isinstance(exc, (OSError, OperationalError, InterfaceError)) or (isinstance(exc, DBAPIError) and exc.connection_invalidated)


@router.get("/bookings")
async def my_bookings(request: Request, group: str | None = None, page: str | None = None, page_size: str | None = None,
                      conn: AsyncConnection = Depends(db)) -> dict:
    """EP-ACC-07. The three parameters are read as text and bounded here so each refusal says its own sentence."""
    if group is not None and group not in ("upcoming", "past"):
        raise ApiError(422, "VALIDATION_FAILED", BAD_GROUP, {"field": "group"})
    page_n = _bounded(page, 1, bk.PAGE_MAX, BAD_PAGE, "page")
    size_n = _bounded(page_size, bk.PAGE_SIZE_DEFAULT, bk.PAGE_SIZE_MAX, BAD_PAGE_SIZE, "page_size")
    try:
        return await bk.my_bookings(conn, user_id=request.state.caller.id, now=request.app.state.clock.now(), group=group,
                                    page=page_n, page_size=size_n)
    except Exception as exc:
        if _down(exc):
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE) from None
        raise


@router.get("/bookings/{reference}")
async def my_booking(request: Request, reference: str, conn: AsyncConnection = Depends(db)) -> dict:
    """EP-ACC-08. Another customer's reference and one that never existed get the same 404, byte for byte."""
    me = request.state.caller
    settings: Settings = request.app.state.settings
    # Fails closed by itself: Redis unreachable is 503 DEPENDENCY_UNAVAILABLE inside enforce (FR-ADR-028).
    await enforce(request, [(LOOKUP_USER, str(me.id)), (LOOKUP_IP, client_ip(request, settings))], UNAVAILABLE)
    stored = bk.normalise_reference(reference)
    found = None
    if stored is not None:
        try:
            found = await bk.my_booking(conn, user_id=me.id, stored_reference=stored, now=request.app.state.clock.now())
        except Exception as exc:
            if _down(exc):
                raise ApiError(503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE) from None
            raise
    if found is None:
        raise ApiError(404, "NOT_FOUND", NOT_YOURS)
    return found

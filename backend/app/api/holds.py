"""Seat holds - EP-HLD-01..04 (P-HLD-01..14). The SIGNED-IN router: any account with an existing user row, of any
role; only the guest is refused (P-HLD-05, PROPOSED-MGRBOOK-01). The check is the router's dependency and no
handler contains one.

Order inside every handler, and why:
  1. a malformed hold token is 400 REQUEST_INVALID before Redis is touched (P-HLD-03 exception 0)
  2. the hold bucket - per user AND per real client IP, in Redis, fail closed (FR-ADR-058)
  3. the domain operation (app/domain/holds)
Redis unreachable anywhere is 503 with the lane's sentence and no further Redis command (SRC-002 §7.9, P-HLD-10):
the except clause below reads nothing, writes nothing and logs nothing that touches Redis.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from redis.exceptions import RedisError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import CurrentUser, current_user, db, get_clock, get_settings
from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.ratelimit import Bucket, client_ip, enforce
from app.domain import holds
from app.domain.money import BIGINT_MAX

log = logging.getLogger("app.holds")

# The seat-hold bucket (EP-HLD-01..04 rate_limit): 20 per minute per user, 60 per minute per real client IP.
HOLD_USER = Bucket("hold:user", "RATE_LIMIT_HOLD_USER_PER_MIN", 60, holds.RATE_LIMITED)
HOLD_IP = Bucket("hold:ip", "RATE_LIMIT_HOLD_IP_PER_MIN", 60, holds.RATE_LIMITED)


async def signed_in(request: Request, conn: AsyncConnection = Depends(db), settings: Settings = Depends(get_settings),
                    clock: Clock = Depends(get_clock)) -> CurrentUser:
    """Any signed-in account. The 401 speaks this lane's sentence for every reason a session is missing or dead
    (P-HLD-05 rows 1 and 2)."""
    try:
        user = await current_user(request, conn, settings, clock)
    except ApiError as exc:
        if exc.status == 401:
            raise ApiError(401, "AUTH_REQUIRED", holds.SIGN_IN) from None
        raise
    request.state.caller = user  # the handlers read it here and declare no dependency of their own
    return user


router = APIRouter(prefix="/api", dependencies=[Depends(signed_in)])

Id = Annotated[int, Path(gt=0, le=BIGINT_MAX)]


class HoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # [JUDGMENT CALL] A ceiling on the list's length so one body cannot make the validation query enormous. Far
    # above MAX_SEATS_PER_BOOKING, so every request a customer can make still gets its published sentence.
    seat_ids: list[StrictInt] = Field(max_length=1000)


def _token(hold_token: str) -> str:
    if not holds.well_formed(hold_token):
        raise ApiError(400, "REQUEST_INVALID", holds.BAD_TOKEN)
    return hold_token


async def _limit(request: Request, user: CurrentUser) -> None:
    await enforce(request, [(HOLD_USER, str(user.id)), (HOLD_IP, client_ip(request, request.app.state.settings))],
                  holds.UNAVAILABLE)


class _Guard:
    """Translate a failure into the lane's envelope: Redis down 503, PostgreSQL down 503, anything else 500."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, kind, exc, tb) -> bool:
        if exc is None or isinstance(exc, ApiError):
            return False
        if isinstance(exc, (RedisError, OSError, OperationalError, InterfaceError)) or (
                isinstance(exc, DBAPIError) and exc.connection_invalidated):
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", holds.UNAVAILABLE) from None
        log.error("hold request failed", exc_info=(kind, exc, tb))
        raise ApiError(500, "INTERNAL_ERROR", holds.FAILED) from None


@router.post("/showtimes/{showtime_id}/holds", status_code=201)
async def create_hold(request: Request, showtime_id: Id, body: HoldRequest, conn: AsyncConnection = Depends(db)) -> dict:
    """EP-HLD-01: all or nothing, ascending seat-id order, the WHOLE hold returned."""
    state, user = request.app.state, request.state.caller
    async with _Guard():
        await _limit(request, user)
        granted = await holds.acquire(state.redis, conn, settings=state.settings, now=state.clock.now(), user_id=user.id,
                                      showtime_id=showtime_id, seat_ids=body.seat_ids, instance_id=state.instance_id)
    state.granted_holds = True  # read by the shutdown hook (app/main.py)
    return granted


# A token carrying `/` is two path segments and reaches no route; app/api/errors.py's not-found handler answers it
# with P-HLD-03's 400 (CR-002 B-13), so the published routes keep plain segments.
@router.get("/holds/{hold_token}")
async def read_hold(request: Request, hold_token: str) -> dict:
    """EP-HLD-02: a reloaded page restores itself. No query and no body: the server takes no client instant."""
    token, user = _token(hold_token), request.state.caller
    async with _Guard():
        await _limit(request, user)
        return await holds.read(request.app.state.redis, token, user.id)


@router.delete("/holds/{hold_token}/seats/{seat_id}")
async def release_seat(request: Request, hold_token: str, seat_id: Id) -> dict:
    """EP-HLD-03: one seat back; the rest keeps its expires_at."""
    token, user = _token(hold_token), request.state.caller
    async with _Guard():
        await _limit(request, user)
        return await holds.release_seat(request.app.state.redis, token, user.id, seat_id)


@router.delete("/holds/{hold_token}", status_code=204)
async def release_hold(request: Request, hold_token: str) -> Response:
    """EP-HLD-04: the whole hold back, 204 and no body."""
    token, user = _token(hold_token), request.state.caller
    async with _Guard():
        await _limit(request, user)
        await holds.release(request.app.state.redis, token, user.id)
    return Response(status_code=204)

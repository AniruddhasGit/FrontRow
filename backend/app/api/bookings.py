"""POST /api/bookings - confirm a held selection into a booking (EP-PAY-01, P-PAY-01, P-PAY-09, P-PAY-10, P-PAY-11).

The router's one dependency is authentication: any signed-in account, of any role, books on its own behalf. No
handler checks a role. The booking is always written against the session's user id, never one from the body.

Order, and why:
  0. the Idempotency-Key header, the body (exactly hold_token + showtime_id, nothing else) and the token's shape are
     checked before Redis is touched - a malformed request is 400 even with Redis down (P-PAY-01 validation)
  1. the confirm bucket: 10 per minute per user AND 30 per minute per real client IP, in Redis, failing closed; a
     replay spends a token like any other request (EP-PAY-01 rate_limit)
  2. ONE PostgreSQL transaction, steps 1-12 of P-PAY-10, in that order (app/domain/booking for the parts)
  3. after the commit: release the hold's locks and record, DEL the seat map, then the bounded queue send - and
     only then the 201 (P-PAY-10 steps 13-15). Nothing is handed to a background task.

THE ONE ROW LOCK on this path is the showtime row's, taken at step 3 so every read of that row inside the
transaction sees one version. It is never used to ask whether a seat is free: the unique constraint answers that.

THE SALES CUT-OFF IS NOT ENFORCED HERE (SRC-003 OPEN-BOOK-03): a customer already holding seats may finish paying.

REDIS DOWN IS 503 and the confirm never looks for a hold anywhere else (SRC-002 §7.9). Every failure inside the
transaction rolls it back in full: no booking, no payment, no idempotency record survives it. The one exception is
the deliberate payment failure, whose `failed` payment row is written afterwards in its own transaction.

THREE OPTIONAL PORTS on app.state, absent in production unless a later phase installs one:
  payment_sleep(ms)       the simulated provider's artificial delay (default: asyncio's sleep)
  confirm_observer(step)  called with each step's name as it starts - instrumentation and fault injection in tests
  receipt_queue(payload)  the post-commit send of the receipt job; with none installed the outbox row stays pending
                          and the worker's relay (Phase 5) sends it
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import CurrentUser, current_user, db, get_clock, get_settings
from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.logging import get_request_id
from app.core.ratelimit import Bucket, client_ip, enforce
from app.domain import booking as bk
from app.domain import holds
from app.domain import payment as pay
from app.domain import reference as refs
from app.domain.booking import ErrorCode
from app.domain.browse.catalogue import local_iso
from app.domain.money import BIGINT_MAX
from app.models import cinema, movie, screen, showtime

log = logging.getLogger("app.bookings")

# The endpoint's whole error set (EP-PAY-01 `errors`); tests/pay/test_s_pay_08.py holds it to the contract.
EMITS = frozenset({
    ErrorCode.REQUEST_INVALID, ErrorCode.AUTH_REQUIRED, ErrorCode.HOLD_EXPIRED, ErrorCode.HOLD_NOT_OWNED,
    ErrorCode.SEAT_UNAVAILABLE,
    ErrorCode.IDEMPOTENCY_IN_FLIGHT,
    ErrorCode.IDEMPOTENCY_KEY_REUSED,
    ErrorCode.PAYMENT_FAILED, ErrorCode.RATE_LIMITED, ErrorCode.DEPENDENCY_UNAVAILABLE, ErrorCode.INTERNAL_ERROR,
})

# The booking-confirm bucket (S7.4): per user and per real client IP, both per minute.
CONFIRM_USER = Bucket("confirm-user", "RATE_LIMIT_CONFIRM_USER_PER_MIN", 60, bk.RATE_LIMITED)
CONFIRM_IP = Bucket("confirm-ip", "RATE_LIMIT_CONFIRM_IP_PER_MIN", 60, bk.RATE_LIMITED)
KEY_MAX = 255  # EP-PAY-01: the header is 1..255 characters


async def confirm_session(request: Request, conn: AsyncConnection = Depends(db), settings: Settings = Depends(get_settings),
                          clock: Clock = Depends(get_clock)) -> CurrentUser:
    """Any signed-in account; the 401 speaks this endpoint's sentence (P-PAY-01 exception 1). The caller is left on
    request.state, so the handler declares no authorisation dependency of its own."""
    try:
        user = await current_user(request, conn, settings, clock)
    except ApiError as exc:
        if exc.status == 401:
            raise ApiError(401, ErrorCode.AUTH_REQUIRED, bk.SIGN_IN) from None
        raise
    request.state.caller = user
    return user


router = APIRouter(dependencies=[Depends(confirm_session)])


class ConfirmRequest(BaseModel):
    """Exactly two properties. Seats come from the hold record and from nowhere else (P-PAY-01)."""

    model_config = ConfigDict(extra="forbid")
    hold_token: StrictStr
    showtime_id: StrictInt = Field(gt=0, le=BIGINT_MAX)


def _bad() -> ApiError:
    # The rejected field's name and value are never echoed into the response or the log (P-PAY-08).
    return ApiError(400, ErrorCode.REQUEST_INVALID, bk.BAD_REQUEST)


async def _body(request: Request) -> ConfirmRequest:
    """Parsed here rather than by the framework, whose refusal is a 422 that names the field (P-PAY-12 exception 2)."""
    try:
        return ConfirmRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise _bad() from None


def _key(request: Request) -> str:
    # Compared as the exact characters received: nothing here trims, folds case or normalises (P-PAY-09).
    key = request.headers.get("idempotency-key")
    if key is None or not 1 <= len(key) <= KEY_MAX:
        raise _bad()
    return key


def _retry_after(settings: Settings) -> str:
    """ceil(PAYMENT_SIMULATED_DELAY_MS / 1000) + 1 (P-PAY-09 worked example): 3 at the configured delay."""
    return str(-(-settings.PAYMENT_SIMULATED_DELAY_MS // 1000) + 1)


def _duplicate(dup: bk.Duplicate, fingerprint: str, settings: Settings) -> Response:
    """P-PAY-09's three answers, and only these."""
    record = dup.record
    if record is not None and record.request_fingerprint != fingerprint:
        raise ApiError(422, ErrorCode.IDEMPOTENCY_KEY_REUSED, bk.KEY_REUSED)
    if record is None or record.status != "completed":
        raise ApiError(409, ErrorCode.IDEMPOTENCY_IN_FLIGHT, bk.IN_FLIGHT, headers={"Retry-After": _retry_after(settings)})
    return Response(bk.canonical_json(record.response_body), status_code=201, media_type="application/json")


def _unavailable(exc: BaseException) -> bool:
    return isinstance(exc, (RedisError, OSError, OperationalError, InterfaceError)) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated)


async def _head(conn: AsyncConnection, showtime_id: int):
    """Step 4: the showtime as the response needs it. No cut-off check (OPEN-BOOK-03)."""
    return (await conn.execute(
        select(showtime.c.starts_at, movie.c.title, screen.c.name.label("screen_name"), cinema.c.timezone)
        .select_from(showtime.join(movie, showtime.c.movie_id == movie.c.id).join(screen, showtime.c.screen_id == screen.c.id)
                     .join(cinema, screen.c.cinema_id == cinema.c.id))
        .where(showtime.c.id == showtime_id))).one()


@router.post("/api/bookings", status_code=201, openapi_extra={"requestBody": {
    "required": True, "content": {"application/json": {"schema": ConfirmRequest.model_json_schema()}}}})
async def confirm(request: Request, conn: AsyncConnection = Depends(db)) -> Response:
    user: CurrentUser = request.state.caller
    key = _key(request)
    body = await _body(request)
    if not holds.well_formed(body.hold_token):
        raise _bad()
    state = request.app.state
    settings: Settings = state.settings
    clock: Clock = state.clock
    observe = getattr(state, "confirm_observer", None) or (lambda step: None)
    sleep = getattr(state, "payment_sleep", None) or (lambda ms: asyncio.sleep(ms / 1000))
    draw = getattr(state, "draw_reference", None) or refs.new_reference
    redis = state.redis
    fingerprint = bk.fingerprint(body.hold_token, body.showtime_id)
    hold = None
    total = 0
    try:
        await enforce(request, [(CONFIRM_USER, str(user.id)), (CONFIRM_IP, client_ip(request, settings))], bk.UNAVAILABLE)
        async with conn.begin():
            observe("idempotency insert")
            record_id = await bk.claim_key(conn, user_id=user.id, key=key, fingerprint_=fingerprint, now=clock.now())
            observe("hold re-validation")
            hold = await holds.load(redis, body.hold_token)
            if hold is None:
                raise ApiError(409, ErrorCode.HOLD_EXPIRED, holds.ENDED)
            if hold.user_id != user.id:
                raise ApiError(403, ErrorCode.HOLD_NOT_OWNED, holds.ENDED)
            if hold.showtime_id != body.showtime_id:
                raise _bad()
            alive = await holds.liveness(redis, hold.showtime_id, sorted(hold.seats), body.hold_token)
            if alive == "expired" or not hold.seats:
                raise ApiError(409, ErrorCode.HOLD_EXPIRED, holds.ENDED)
            if alive == "not_owned":
                raise ApiError(403, ErrorCode.HOLD_NOT_OWNED, holds.ENDED)
            observe("showtime lock")
            await conn.execute(text("SELECT id FROM showtime WHERE id = :id FOR UPDATE"), {"id": hold.showtime_id})
            observe("showtime read")
            head = await _head(conn, hold.showtime_id)
            observe("price sum")
            lines = bk.snapshot(hold)
            total = sum(line["price_paise"] for line in lines)
            observe("payment capture")
            payment_id = await pay.take(conn, amount_paise=total, idempotency_key=key, fail_prefix=settings.PAYMENT_SIMULATOR_FAIL_KEY_PREFIX,
                                        delay_ms=settings.PAYMENT_SIMULATED_DELAY_MS, sleep=sleep, now=clock.now)
            observe("booking insert")
            now = clock.now()
            booking_id, ref = await bk.insert_booking(conn, user_id=user.id, showtime_id=hold.showtime_id, payment_id=payment_id,
                                                      total_paise=total, lines=lines, now=now, draw=draw)
            observe("audit")  # step 8: a customer booking is not a privileged action, so no audit row is written
            observe("receipt_dispatch insert")
            observe("outbox_message insert")
            outbox_id = await bk.write_receipt_job(conn, booking_id=booking_id, request_id=get_request_id(), now=now)
            observe("idempotency completed")
            response = {
                "booking_id": booking_id, "booking_reference": bk.presentation(ref), "showtime_id": hold.showtime_id,
                "movie_title": head.title, "screen_name": head.screen_name, "starts_at": local_iso(head.starts_at, head.timezone),
                "seats": [{k: line[k] for k in ("seat_id", "seat_label", "seat_category_name", "price_paise",
                                                "base_price_paise_applied", bk.APPLIED_UPLIFT)} for line in lines],
                "total_paise": total, "currency_code": settings.CURRENCY_CODE, "payment_status": "captured",
                "created_at": local_iso(now, head.timezone),
            }
            await bk.complete_key(conn, record_id, booking_id=booking_id, body=response, now=now)
            observe("commit")
        # ---- committed. Nothing below can undo the booking, so nothing below may turn it into an error: each
        # failure from here on is logged and the 201 still goes out. The locks expire within the hold's TTL, the
        # outbox row stays pending for the relay, and a replay with the same key returns the stored body. ----
        try:
            observe("release")
            await holds.release_all(redis, hold)  # compare-and-delete each lock, the record, the index; then DEL the map
        except Exception:  # noqa: BLE001
            log.warning("post-commit hold release failed; the locks expire within the hold's TTL", exc_info=True)
        try:
            observe("queue send")
            await _send_receipt(state, settings, clock, conn, outbox_id, booking_id)
        except Exception:  # noqa: BLE001
            log.warning("post-commit receipt send failed; the outbox row stays pending for the relay", exc_info=True)
        return Response(bk.canonical_json(response), status_code=201, media_type="application/json")
    except bk.Duplicate as dup:
        return _duplicate(dup, fingerprint, settings)
    except pay.PaymentFailed:
        # The booking transaction has rolled back (its idempotency record with it); the attempt itself is recorded.
        async with conn.begin():
            await pay.record_failure(conn, amount_paise=total, idempotency_key=key, now=clock.now())
        raise ApiError(402, ErrorCode.PAYMENT_FAILED, bk.PAYMENT_FAILED) from None
    except bk.SeatsTaken:
        # The guard working (P-PAY-11): expected, logged at info, never retried.
        # A violation means a committed row exists, so this read finds at least one seat. Should it ever find none,
        # the hold's own seats are named rather than the refusal crashing into a 500.
        labels = await bk.sold_labels(conn, hold.showtime_id, hold) or [hold.seats[i]["label"] for i in sorted(hold.seats)]
        log.info("seat taken at confirm", extra={"error_code": ErrorCode.SEAT_UNAVAILABLE.value, "unavailable_seats": labels})
        raise ApiError(409, ErrorCode.SEAT_UNAVAILABLE, bk.taken_message(labels), {"unavailable_seats": labels}) from None
    except ApiError:
        raise
    except Exception as exc:
        if _unavailable(exc):
            raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE, bk.UNAVAILABLE) from None
        log.error("confirm failed", exc_info=True)
        raise ApiError(500, ErrorCode.INTERNAL_ERROR, bk.FAILED) from None


async def _send_receipt(state, settings: Settings, clock: Clock, conn: AsyncConnection, outbox_id: int, booking_id: int) -> None:
    """P-PAY-10 step 15: bounded by QUEUE_SEND_TIMEOUT_MS. Any failure leaves the outbox row pending for the relay."""
    queue = getattr(state, "receipt_queue", None)
    if queue is None:
        return
    try:
        await asyncio.wait_for(queue(bk.outbox_payload(booking_id, get_request_id())), timeout=settings.QUEUE_SEND_TIMEOUT_MS / 1000)
        await bk.mark_sent(conn, outbox_id, clock.now())
    except Exception:  # noqa: BLE001 - the booking is committed; the relay sends what this leaves behind
        log.warning("receipt fast-path send failed; the outbox row stays pending for the relay", exc_info=True)

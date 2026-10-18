"""EP-TKT-01 GET /api/bookings/by-reference/{reference} and EP-TKT-02 POST .../resend-receipt (P-TKT-02, P-TKT-07, P-TKT-09).

AUTHORISATION ONCE, ON THE ROUTER. `owned_reference` is the router's one dependency: it normalises the typed
reference, resolves the caller from the session, and admits the request only when booking.user_id equals the caller's
id - in ONE equality predicate (reference = :r AND user_id = :caller). The role is never consulted: there is no admin
override (EP-TKT-01 authorisation_rule). The handlers below carry no ownership check of their own (S-TKT-03).

NO ENUMERATION ORACLE. A malformed reference, an unknown one and another customer's all raise the same 404 with the same
sentence; only the per-request request_id differs. A reference that cannot be one (non-ASCII, over 64 characters, or
outside the alphabet after normalising) is refused before the database is touched (S-TKT-02: 0 queries).

NOTHING HERE READS OR SHOWS THE DISPATCH STATE to the customer except the resend's own outcome (P-TKT-09/10).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request, Response
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import CurrentUser, current_user, db, get_clock, get_settings
from app.api.errors import ApiError
from app.api.me import LOOKUP_IP, LOOKUP_USER, NOT_YOURS, SIGN_IN
from app.core.clock import Clock
from app.core.config import Settings
from app.core.logging import get_request_id
from app.core.ratelimit import Bucket, client_ip, enforce
from app.domain import booking as bk
from app.domain.browse.catalogue import local_iso

log = logging.getLogger("app.receipts")

UNAVAILABLE = "This page is unavailable right now. Your booking is not affected."
SUPPRESSED = ("This is demonstration data. No receipt was sent for this booking and none can be — the address is a "
              "placeholder, not a real inbox.")
MAX_TYPED = 64  # EP-TKT-01: the path parameter is 1..64 characters


class _Interval(Bucket):
    """One accepted resend per RECEIPT_RESEND_MIN_INTERVAL_SECONDS per booking: a bucket of capacity 1 whose window is
    the configured interval (EP-TKT-02 rate_limit), on the same injected-clock token bucket as every other limiter."""

    def sized(self, settings: Settings) -> Bucket:
        return Bucket(self.name, self.setting, getattr(settings, self.setting), self.message, 1)


RESEND_BOOKING = _Interval("resend-booking", "RECEIPT_RESEND_MIN_INTERVAL_SECONDS", 0,
                           "A receipt was requested recently. You can request another in {span}.")


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", NOT_YOURS)


async def _limit(request: Request, checks: list[tuple[Bucket, str]]) -> None:
    """Fail closed: Redis unreachable is 503, never a pass (FR-ADR-028)."""
    try:
        await enforce(request, checks, UNAVAILABLE)
    except RedisError:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE) from None


async def owned_reference(request: Request, conn: AsyncConnection = Depends(db), settings: Settings = Depends(get_settings),
                          clock: Clock = Depends(get_clock)) -> CurrentUser:
    """The router's ONE dependency: the caller, admitted only for a booking they own."""
    typed = request.path_params.get("reference", "")
    # Shape first, before the session or the database: isascii() so no non-ASCII character can fold onto an alphabet
    # member when uppercased (U+FB00 'ﬀ' uppercases to 'FF'); the length bound is EP-TKT-01's.
    stored = bk.normalise_reference(typed) if typed.isascii() and 1 <= len(typed) <= MAX_TYPED else None
    if stored is None:
        raise _not_found()
    try:
        user = await current_user(request, conn, settings, clock)
    except ApiError as exc:
        if exc.status == 401:
            raise ApiError(401, "AUTH_REQUIRED", SIGN_IN) from None
        raise
    if request.method == "GET":
        # EP-TKT-01's buckets. The resend spends its tokens itself, and only when it accepts: a refused resend - a
        # suppressed row pressed a hundred times - must spend nothing (EP-TKT-02 idempotency, S-TKT-10).
        await _limit(request, [(LOOKUP_USER, str(user.id)), (LOOKUP_IP, client_ip(request, settings))])
    booking_id = (await conn.execute(text("SELECT id FROM booking WHERE reference = :r AND user_id = :u"),
                                     {"r": stored, "u": user.id})).scalar()
    await conn.rollback()
    if booking_id is None:
        raise _not_found()
    return user


router = APIRouter(prefix="/api/bookings/by-reference", dependencies=[Depends(owned_reference)])


def _stored(request: Request, reference: str) -> str:
    # Re-normalised here rather than read from the dependency's state, so the handler has no ownership logic in it and
    # no hidden coupling: replacing the dependency with a pass-through leaves a handler that still works (S-TKT-03).
    stored = bk.normalise_reference(reference) if reference.isascii() else None
    if stored is None:
        raise _not_found()
    return stored


@router.get("/{reference}")
async def read(request: Request, reference: str, conn: AsyncConnection = Depends(db)) -> dict:
    """EP-TKT-01: exactly the eight keys a door needs. No status, no dispatch state."""
    stored = _stored(request, reference)
    row = (await conn.execute(text(
        "SELECT b.id, b.reference, b.total_paise, m.title, sc.name AS hall, st.starts_at, c.timezone, p.captured_at, u.email "
        "FROM booking b JOIN showtime st ON st.id = b.showtime_id JOIN movie m ON m.id = st.movie_id "
        "JOIN screen sc ON sc.id = st.screen_id JOIN cinema c ON c.id = sc.cinema_id JOIN payment p ON p.id = b.payment_id "
        "JOIN users u ON u.id = b.user_id WHERE b.reference = :r"), {"r": stored})).first()
    if row is None:
        await conn.rollback()
        raise _not_found()
    seats = (await conn.execute(text(
        "SELECT s.row_label, s.seat_number FROM booking_seat bs JOIN seat s ON s.id = bs.seat_id WHERE bs.booking_id = :b "
        "ORDER BY s.row_label, s.seat_number"), {"b": row.id})).all()
    await conn.rollback()
    return {"reference": bk.presentation(row.reference), "film_title": row.title, "hall_name": row.hall,
            "starts_at": local_iso(row.starts_at, row.timezone), "seats": [f"{s.row_label}{s.seat_number}" for s in seats],
            "total_paise": row.total_paise, "paid_at": local_iso(row.captured_at, row.timezone) if row.captured_at else None,
            "receipt_email_address": row.email}


@router.post("/{reference}/resend-receipt", status_code=202)
async def resend(request: Request, reference: str, conn: AsyncConnection = Depends(db)) -> Response:
    """EP-TKT-02 / P-TKT-07. One transaction: lock the dispatch row, decide, and - only when a send completed or failed -
    raise dispatch_seq, return the row to pending and insert exactly one receipt.send outbox row. No audit row: a customer
    resend is not a privileged action. Refusals spend no rate-limit token."""
    state = request.app.state
    settings: Settings = state.settings
    clock: Clock = state.clock
    stored = _stored(request, reference)
    async with conn.begin():
        row = (await conn.execute(text(
            "SELECT rd.id, rd.booking_id, rd.status, rd.attempts, rd.dispatch_seq, u.id AS user_id, u.email FROM receipt_dispatch rd "
            "JOIN booking b ON b.id = rd.booking_id JOIN users u ON u.id = b.user_id WHERE b.reference = :r FOR UPDATE OF rd"),
            {"r": stored})).first()
        if row is None:
            raise _not_found()
        if row.status == "suppressed":
            raise ApiError(409, "RECEIPT_SUPPRESSED", SUPPRESSED)
        if row.status not in ("sent", "failed"):
            # pending (first receipt not attempted yet, or a resend in flight) or sending: nothing to enqueue.
            return _accepted(False, row.email)
        # Accepting: the per-booking interval and the owner's lookup bucket, both or neither (EP-TKT-02 rate_limit).
        await _limit(request, [(RESEND_BOOKING, str(row.booking_id)), (LOOKUP_USER, str(row.user_id))])
        seq = row.dispatch_seq + 1
        await conn.execute(text("UPDATE receipt_dispatch SET dispatch_seq = :s, status = 'pending' WHERE id = :id"),
                           {"s": seq, "id": row.id})
        payload = {**bk.outbox_payload(row.booking_id, get_request_id()), "dispatch_seq": seq}
        outbox_id = (await conn.execute(text(
            "INSERT INTO outbox_message (topic, payload, status, attempts, created_at) "
            "VALUES ('receipt.send', CAST(:p AS jsonb), 'pending', 0, :at) RETURNING id"),
            {"p": bk.canonical_json(payload).decode(), "at": clock.now()})).scalar_one()
    await _fast_path(state, settings, clock, conn, outbox_id, payload)
    return _accepted(True, row.email)


def _accepted(queued: bool, email: str) -> Response:
    return Response(bk.canonical_json({"queued": queued, "email_address": email}), status_code=202, media_type="application/json")


async def _fast_path(state, settings: Settings, clock: Clock, conn: AsyncConnection, outbox_id: int, payload: dict) -> None:
    """The same bounded post-commit send the confirm makes (P-TKT-04 step 3); a failure leaves the row for the relay."""
    queue = getattr(state, "receipt_queue", None)
    if queue is None:
        return
    try:
        await asyncio.wait_for(queue(payload), timeout=settings.QUEUE_SEND_TIMEOUT_MS / 1000)
        await bk.mark_sent(conn, outbox_id, clock.now())
    except Exception:  # noqa: BLE001 - committed; the relay sends what this leaves behind
        log.error("resend fast-path send failed; the outbox row stays pending for the relay", exc_info=True)


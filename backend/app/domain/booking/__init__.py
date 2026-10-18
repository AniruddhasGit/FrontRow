"""Booking confirmation (P-PAY-09, P-PAY-10, P-PAY-11, P-TKT-01, P-TKT-04) - everything the confirm does except the
transaction's single row lock and its HTTP edges, which app/api/bookings.py owns.

The idempotency guard: the record is inserted FIRST, inside the booking transaction, under UNIQUE(user_id,
idempotency_key). A transaction-scoped advisory lock on the same pair is taken immediately before the insert with
pg_try_advisory_xact_lock, which never waits: a second request whose first is still running gets False at once and
is answered 409 IDEMPOTENCY_IN_FLIGHT instead of queueing behind the first one's uncommitted row (an INSERT that
meets an uncommitted duplicate blocks until that transaction ends - P-PAY-09 "the second request is never made to
wait"). The unique index stays the guard: the lock only decides whether to wait, never whether a row may exist.

The seat guard is UNIQUE(showtime_id, seat_id) on booking_seat. A violation is the guard working: it is caught,
translated into 409 SEAT_UNAVAILABLE, logged at info, and never retried (P-PAY-11). There is one INSERT INTO
booking_seat per attempt and no conflict clause anywhere on this path.

The record of a confirm is never removed by anything in this product (FR-ADR-012).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain import reference as refs
from app.domain.holds import Hold
from app.domain.pricing import UPLIFT_COLUMN
from app.models import booking, booking_seat, idempotency_record, outbox_message, receipt_dispatch, seat

# The snapshot column/key for the uplift a seat was priced at; the name is built from pricing.py's, so the column
# name appears nowhere outside pricing.py and the models (S-XCT-05).
APPLIED_UPLIFT = UPLIFT_COLUMN + "_applied"
# P-TKT-04: the receipt job's payload version. One version exists.
MESSAGE_VERSION = 1
# P-TKT-01 step 3: five draws in total, then 500.
REFERENCE_ATTEMPTS = 5
# The unique constraints whose violation this module translates (schema.sql).
SEAT_GUARD = "uq_booking_seat__showtime_id_seat_id"
REFERENCE_GUARD = "uq_booking__reference"
IDEMPOTENCY_GUARD = "uq_idempotency_record__user_id_idempotency_key"


class ErrorCode(StrEnum):
    """The registry codes the confirm endpoint can emit (EP-PAY-01 `errors`). SALES_CLOSED is deliberately absent."""

    REQUEST_INVALID = "REQUEST_INVALID"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    HOLD_NOT_OWNED = "HOLD_NOT_OWNED"
    SEAT_UNAVAILABLE = "SEAT_UNAVAILABLE"
    IDEMPOTENCY_IN_FLIGHT = "IDEMPOTENCY_IN_FLIGHT"
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---- the lane's own sentences (P-PAY-01, P-PAY-09; the four hold codes are P-HLD-14's, in app/domain/holds) ----
SIGN_IN = "Sign in to complete this booking."
BAD_REQUEST = "This request could not be processed. Return to the seat map and choose your seats again."
IN_FLIGHT = "This booking is still being processed."
KEY_REUSED = "This checkout is out of date. Return to the seat map and choose your seats again."
PAYMENT_FAILED = ("The payment did not go through and you have not been charged. You can try again while the countdown is "
                  "still running. If it has reached zero your hold has ended and you will need to choose your seats again.")
FAILED = "Something went wrong and your booking was not completed. No payment was taken. If you need help, quote {request_id}."
UNAVAILABLE = ("We cannot complete your booking right now. You have not been charged. Try again in a few minutes. "
               "If you need help, quote {request_id}.")
RATE_LIMITED = "Too many attempts. Try again in {span}."


class Duplicate(Exception):
    """Step 1 found the key already used by this user. `record` is the committed row, or None while it is in flight."""

    def __init__(self, record) -> None:
        self.record = record


class SeatsTaken(Exception):
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels


class BrokenHold(Exception):
    """The hold record cannot be booked as it stands - a seat with no price snapshot. A defect, answered 500."""


class ReferenceExhausted(Exception):
    """Five draws, five collisions (P-TKT-01 exception 2)."""


def fingerprint(hold_token: str, showtime_id: int) -> str:
    """sha256 of the canonicalised body: exactly the two fields EP-PAY-01 accepts."""
    canonical = json.dumps({"hold_token": hold_token, "showtime_id": showtime_id}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def canonical_json(body: dict) -> bytes:
    """The one serialisation of a confirm response: the first answer and every replay are the same bytes."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def presentation(stored: str) -> str:
    """FR-XXXX-XXXX from the 8 stored characters (P-TKT-01: the prefix and hyphen are presentation only)."""
    return f"FR-{stored[:4]}-{stored[4:]}"


def taken_message(labels: list[str]) -> str:
    """P-HLD-14 rows 4 and 4b, the at-confirm sentences."""
    from app.domain.holds import joined

    verb = "was" if len(labels) == 1 else "were"
    return (f"{joined(labels)} {verb} taken by another customer before your payment finished. "
            "Your booking was not made and you have not been charged.")


# ---- step 1 -----------------------------------------------------------------------------------------------------


async def claim_key(conn: AsyncConnection, *, user_id: int, key: str, fingerprint_: str, now: datetime) -> int:
    """Insert the record (in_progress). Raises Duplicate when the key is in flight or already committed."""
    got = (await conn.execute(select(func.pg_try_advisory_xact_lock(func.hashtextextended(f"{user_id}:{key}", 0))))).scalar_one()
    if not got:
        raise Duplicate(None)
    try:
        async with conn.begin_nested():
            return (await conn.execute(insert(idempotency_record).values(
                user_id=user_id, idempotency_key=key, request_fingerprint=fingerprint_, status="in_progress", created_at=now)
                .returning(idempotency_record.c.id))).scalar_one()
    except IntegrityError as exc:
        if _constraint(exc) != IDEMPOTENCY_GUARD:
            raise
    record = (await conn.execute(select(idempotency_record.c.status, idempotency_record.c.request_fingerprint,
                                        idempotency_record.c.response_body)
                                 .where(idempotency_record.c.user_id == user_id, idempotency_record.c.idempotency_key == key))).first()
    raise Duplicate(record)


async def complete_key(conn: AsyncConnection, record_id: int, *, booking_id: int, body: dict, now: datetime) -> None:
    await conn.execute(update(idempotency_record).where(idempotency_record.c.id == record_id)
                       .values(status="completed", booking_id=booking_id, response_body=body, completed_at=now))


# ---- step 5 -----------------------------------------------------------------------------------------------------


def snapshot(hold: Hold) -> list[dict]:
    """The hold's per-seat price snapshot, ascending by seat id. Nothing is recomputed (P-PAY-05)."""
    lines = []
    for seat_id, entry in sorted(hold.seats.items()):
        try:
            lines.append({"seat_id": seat_id, "seat_label": entry["label"], "seat_category_name": entry["category"],
                          "seat_category_id": entry["category_id"], "price_paise": entry["price_paise"],
                          "base_price_paise_applied": entry["base_price_paise"], APPLIED_UPLIFT: entry["uplift_bp"]})
        except KeyError:
            raise BrokenHold() from None
        if type(lines[-1]["price_paise"]) is not int:
            raise BrokenHold()
    if not lines:
        raise BrokenHold()
    return lines


# ---- step 7 -----------------------------------------------------------------------------------------------------


def _constraint(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    return diag


async def insert_booking(conn: AsyncConnection, *, user_id: int, showtime_id: int, payment_id: int, total_paise: int,
                         lines: list[dict], now: datetime, draw: Callable[[], str]) -> tuple[int, str]:
    """The booking row under a fresh reference (at most five draws), then every booking_seat row in ONE insert."""
    for _ in range(REFERENCE_ATTEMPTS):
        ref = draw()
        if not refs.is_valid(ref):
            raise ValueError("the reference generator produced an invalid reference")  # a defect, never corrected
        try:
            async with conn.begin_nested():
                booking_id = (await conn.execute(insert(booking).values(
                    reference=ref, user_id=user_id, showtime_id=showtime_id, payment_id=payment_id, total_paise=total_paise,
                    status="confirmed", created_at=now).returning(booking.c.id))).scalar_one()
            break
        except IntegrityError as exc:
            if _constraint(exc) != REFERENCE_GUARD:
                raise
    else:
        raise ReferenceExhausted()
    try:
        async with conn.begin_nested():
            written = (await conn.execute(insert(booking_seat).values([
                {"booking_id": booking_id, "showtime_id": showtime_id, "seat_id": line["seat_id"], "price_paise": line["price_paise"],
                 "base_price_paise_applied": line["base_price_paise_applied"],
                 APPLIED_UPLIFT: line[APPLIED_UPLIFT],
                 "seat_category_id": line["seat_category_id"], "created_at": now} for line in lines]).returning(booking_seat.c.id))).all()
    except IntegrityError as exc:
        if _constraint(exc) != SEAT_GUARD:
            raise
        raise SeatsTaken([]) from None
    if len(written) != len(lines):
        raise BrokenHold()
    return booking_id, ref


async def sold_labels(conn: AsyncConnection, showtime_id: int, hold: Hold) -> list[str]:
    """After the rollback: which of the hold's seats now carry a committed booking_seat row, in hold order."""
    ids = sorted(hold.seats)
    sold = set((await conn.execute(select(booking_seat.c.seat_id).where(booking_seat.c.showtime_id == showtime_id,
                                                                         booking_seat.c.seat_id.in_(ids)))).scalars())
    await conn.rollback()
    return [hold.seats[i]["label"] for i in ids if i in sold]


# ---- steps 9 and 10 ---------------------------------------------------------------------------------------------


async def write_receipt_job(conn: AsyncConnection, *, booking_id: int, request_id: str, now: datetime) -> int:
    """receipt_dispatch (dispatch_seq 1, pending) and its outbox row, in the caller's transaction. Returns the outbox id."""
    await conn.execute(insert(receipt_dispatch).values(booking_id=booking_id, status="pending", dispatch_seq=1, attempts=0,
                                                       created_at=now))
    return (await conn.execute(insert(outbox_message).values(topic="receipt.send", payload=outbox_payload(booking_id, request_id), status="pending", attempts=0,
                                                             created_at=now).returning(outbox_message.c.id))).scalar_one()


async def mark_sent(conn: AsyncConnection, outbox_id: int, now: datetime) -> None:
    async with conn.begin():
        await conn.execute(update(outbox_message).where(outbox_message.c.id == outbox_id, outbox_message.c.status == "pending")
                           .values(status="sent", sent_at=now))


def outbox_payload(booking_id: int, request_id: str) -> dict:
    return {"booking_id": booking_id, "dispatch_seq": 1, "request_id": request_id, "message_version": MESSAGE_VERSION}



# ---- the caller's own bookings (EP-ACC-07, EP-ACC-08, P-ACC-10..12) ----------------------------------------------
# Every query below carries the caller's user id in the SAME statement as everything else it filters on: there is
# no read of a booking followed by a check of whose it is (EP-ACC-08 authorisation_rule).

PAGE_MAX, PAGE_SIZE_MAX, PAGE_SIZE_DEFAULT = 1000, 50, 20


def normalise_reference(typed: str) -> str | None:
    """EP-ACC-08 / FR-ADR-015: case, hyphens and whitespace ignored, the FR prefix optional. Nothing is corrected - a
    character outside the alphabet stays itself, so the result is simply not a reference (None) and the lookup 404s."""
    squeezed = "".join(ch for ch in typed if ch != "-" and not ch.isspace()).upper()
    if len(squeezed) == refs.LENGTH + 2 and squeezed.startswith("FR"):
        squeezed = squeezed[2:]
    return squeezed if refs.is_valid(squeezed) else None


def _summary_rows(user_id: int):
    from app.models import cinema, movie, screen, showtime

    seats = (select(func.count().label("n")).select_from(booking_seat).where(booking_seat.c.booking_id == booking.c.id)
             .scalar_subquery())
    return (select(booking.c.id, booking.c.reference, booking.c.total_paise, booking.c.created_at, movie.c.title,
                   screen.c.name.label("hall"), showtime.c.starts_at, showtime.c.ends_at, cinema.c.timezone, seats.label("seat_count"))
            .select_from(booking.join(showtime, booking.c.showtime_id == showtime.c.id).join(movie, showtime.c.movie_id == movie.c.id)
                         .join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id))
            .where(booking.c.user_id == user_id))


async def my_bookings(conn: AsyncConnection, *, user_id: int, now: datetime, group: str | None, page: int, page_size: int) -> dict:
    """Both arrays always present; page and page_size applied to each group against its own total (EP-ACC-07)."""
    from app.domain.browse.catalogue import local_iso
    from app.models import showtime

    totals = (await conn.execute(select(
        func.count().filter(showtime.c.ends_at > now).label("upcoming"), func.count().filter(showtime.c.ends_at <= now).label("past"))
        .select_from(booking.join(showtime, booking.c.showtime_id == showtime.c.id)).where(booking.c.user_id == user_id))).one()
    out: dict = {"upcoming": [], "past": [], "page": page, "page_size": page_size,
                 "total_upcoming": totals.upcoming, "total_past": totals.past}
    base = _summary_rows(user_id)
    plans = {"upcoming": (showtime.c.ends_at > now, showtime.c.starts_at.asc()),
             "past": (showtime.c.ends_at <= now, showtime.c.starts_at.desc())}
    for name, (where, first) in plans.items():
        if group not in (None, name):
            continue
        rows = (await conn.execute(base.where(where).order_by(first, booking.c.created_at.desc(), booking.c.id.asc())
                                   .limit(page_size).offset((page - 1) * page_size))).all()
        labels = await _labels(conn, [r.id for r in rows])
        out[name] = [{"reference": presentation(r.reference), "movie_title": r.title, "hall_name": r.hall, "seat_count": r.seat_count,
                      "group": name, "showtime_starts_at": local_iso(r.starts_at, r.timezone),
                      "showtime_ends_at": local_iso(r.ends_at, r.timezone), "booked_at": local_iso(r.created_at, r.timezone),
                      "seats": labels.get(r.id, []), "total_paise": r.total_paise} for r in rows]
    await conn.rollback()
    return out


async def _labels(conn: AsyncConnection, booking_ids: list[int]) -> dict[int, list[str]]:
    """Seat labels per booking, by row then seat number as an integer (P-ACC-10: F2 before F10)."""
    if not booking_ids:
        return {}
    rows = (await conn.execute(select(booking_seat.c.booking_id, seat.c.row_label, seat.c.seat_number)
                               .select_from(booking_seat.join(seat, booking_seat.c.seat_id == seat.c.id))
                               .where(booking_seat.c.booking_id.in_(booking_ids))
                               .order_by(booking_seat.c.booking_id, seat.c.row_label, seat.c.seat_number))).all()
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r.booking_id, []).append(f"{r.row_label}{r.seat_number}")
    return out


async def my_booking(conn: AsyncConnection, *, user_id: int, stored_reference: str, now: datetime) -> dict | None:
    """ONE statement: the booking, its showtime and every seat, WHERE reference = :r AND user_id = :caller."""
    from app.domain.browse.catalogue import local_iso
    from app.models import cinema, movie, screen, seat_category, showtime

    rows = (await conn.execute(
        select(booking.c.reference, booking.c.total_paise, booking.c.created_at, movie.c.title, screen.c.name.label("hall"),
               showtime.c.starts_at, showtime.c.ends_at, cinema.c.timezone, seat.c.row_label, seat.c.seat_number,
               seat_category.c.name.label("category"), booking_seat.c.price_paise)
        .select_from(booking.join(showtime, booking.c.showtime_id == showtime.c.id).join(movie, showtime.c.movie_id == movie.c.id)
                     .join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id)
                     .join(booking_seat, booking_seat.c.booking_id == booking.c.id).join(seat, booking_seat.c.seat_id == seat.c.id)
                     .join(seat_category, booking_seat.c.seat_category_id == seat_category.c.id))
        .where(booking.c.reference == stored_reference, booking.c.user_id == user_id)
        .order_by(seat.c.row_label, seat.c.seat_number))).all()
    await conn.rollback()
    if not rows:
        return None
    r = rows[0]
    return {"reference": presentation(r.reference), "movie_title": r.title, "hall_name": r.hall,
            "showtime_starts_at": local_iso(r.starts_at, r.timezone), "showtime_ends_at": local_iso(r.ends_at, r.timezone),
            "seats": [{"seat_label": f"{x.row_label}{x.seat_number}", "seat_category_name": x.category, "price_paise": x.price_paise}
                      for x in rows],
            "total_paise": r.total_paise, "booked_at": local_iso(r.created_at, r.timezone),
            "group": "upcoming" if now < r.ends_at else "past"}

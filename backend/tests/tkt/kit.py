"""Fixtures for the worker lane (S-TKT-05..15, S-SCP-15, S-XCT-25): the real Worker against a throwaway migrated
database connected as frontrow_app, with every collaborator a recording stub and the clock injected.

THE BOOKING (the PRD's own worked example, P-TKT-03 / P-TKT-06 / SCR-TKT-02): reference ACDEFHJD, film DEMO MOVIE 01,
Hall 3, showtime stored 2026-08-21T13:45:00Z in an Asia/Kolkata cinema, three Premium seats inserted F9, F7, F8, total
84372 paise (28124 x 3), and its receipt_dispatch row exactly as the booking transaction writes it (P-TKT-04 step 1).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import psycopg

from app.db import make_engine
from app.workers import Worker
from app.workers.queue import Message
from tests.conftest import FakeClock
from tests.dbkit import FAKE_HASH, app_settings, owner_sql

REFERENCE = "ACDEFHJD"
STARTS = "2026-08-21T13:45:00Z"
TOTAL = 84372
EMAIL = "name@example.com"


class Clock(FakeClock):
    """FakeClock set to a given instant."""

    def __init__(self, at: str = "2026-08-21T10:00:00Z") -> None:
        super().__init__()
        self._now = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(timezone.utc)


class Queue:
    """The queue stub: records every SendMessage, holds what it was given, and deletes only what the worker deletes."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.held: list[Message] = []
        self.deleted: list[str] = []
        self.fail = False

    async def send(self, topic: str, body: dict) -> None:
        self.sent.append((topic, body))
        if self.fail:
            raise ConnectionError("queue unreachable (stub)")

    async def receive(self, max_messages: int) -> list[Message]:
        return list(self.held[:max_messages])

    async def remove(self, message: Message) -> None:
        self.deleted.append(message.id)
        self.held = [m for m in self.held if m.id != message.id]


class Mail:
    """The mail-port stub: records every send. `refuse` makes it answer with an error; `block` makes it never answer."""

    REFUSAL = "SES MessageRejected: Email address is not verified."

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.refuse = False
        self.block = False

    async def send(self, to, message) -> str:
        from app.domain.mail import MailRefused

        self.calls.append((to, message))
        if self.block:
            await asyncio.Event().wait()
        if self.refuse:
            raise MailRefused(self.REFUSAL)
        return f"ses-{len(self.calls)}"


class Bound:
    """The worker's `within(ms, awaitable)`, against the injected clock: a call that completes at once returns; a call that
    blocks is abandoned by moving the injected clock to exactly the bound, so no test spends real time."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.bounds: list[int] = []
        self.abandoned_at: list[datetime] = []

    async def __call__(self, ms: int, awaitable):
        self.bounds.append(ms)
        task = asyncio.ensure_future(awaitable)
        for _ in range(5):
            await asyncio.sleep(0)
            if task.done():
                return task.result()
        task.cancel()
        self.clock.advance(ms / 1000)
        self.abandoned_at.append(self.clock.now())
        raise TimeoutError


def worker(db, clock, queue=None, mail=None, **overrides: str):
    """A Worker on its own engine. The caller disposes `w.engine`."""
    settings = app_settings(db, **{"PUBLIC_BASE_URL": "https://example.invalid", **overrides})
    w = Worker(settings, clock, make_engine(settings), queue or Queue(), mail or Mail(), within=Bound(clock))
    return w


def message(booking_id: int, dispatch_seq: int = 1, topic: str = "receipt.send", request_id: str = "a1b2c3d4", **extra) -> Message:
    body = {"booking_id": booking_id, "dispatch_seq": dispatch_seq, "request_id": request_id, "message_version": 1, **extra}
    return Message(id=uuid.uuid4().hex, topic=topic, body=body, receipt_handle=uuid.uuid4().hex)


def reset_message(token_id: int, user_id: int, token: str = "TESTTOKENVALUE0001") -> Message:
    body = {"user_id": user_id, "reset_token_id": token_id, "request_id": "a1b2c3d4", "message_version": 1, "reset_token": token}
    return Message(id=uuid.uuid4().hex, topic="password_reset.send", body=body, receipt_handle=uuid.uuid4().hex)


def truncate(db) -> None:
    owner_sql(db, "TRUNCATE outbox_message, receipt_dispatch, password_reset_token, idempotency_record, booking_seat, booking, "
                  "payment, audit_log, showtime_seat, showtime, movie_genre, movie, seat, screen, cinema, seat_category, "
                  "language, certification, genre, format, users RESTART IDENTITY CASCADE")


def booking(db, *, reference: str = REFERENCE, email: str = EMAIL, dispatch: str | None = "pending") -> int:
    """The worked-example booking. dispatch=None writes no receipt_dispatch row."""
    tag = uuid.uuid4().hex[:8]
    with psycopg.connect(db.owner_url) as conn, conn.transaction():
        q = lambda sql, p=None: conn.execute(sql, p).fetchone()[0]  # noqa: E731
        uid = q("INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, 'customer', 1) RETURNING id",
                (email, FAKE_HASH))
        cinema = q("INSERT INTO cinema (name, timezone, version) VALUES (%s, 'Asia/Kolkata', 1) RETURNING id", (f"Venue {tag}",))
        screen = q("INSERT INTO screen (cinema_id, name, version) VALUES (%s, 'Hall 3', 1) RETURNING id", (cinema,))
        premium = q("INSERT INTO seat_category (name, uplift_basis_points, version) VALUES (%s, 1250, 1) RETURNING id", (f"Premium {tag}",))
        cert = q("INSERT INTO certification (name, is_active) VALUES (%s, true) RETURNING id", (f"Cert {tag}",))
        lang = q("INSERT INTO language (name, is_active) VALUES (%s, true) RETURNING id", (f"Lang {tag}",))
        movie = q("INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, version) "
                  "VALUES ('DEMO MOVIE 01', 'Demonstration film.', 120, %s, %s, 1) RETURNING id", (cert, lang))
        st = q("INSERT INTO showtime (movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version) "
               "VALUES (%s, %s, %s, %s::timestamptz + interval '2 hours', 24999, 3, 1) RETURNING id", (movie, screen, STARTS, STARTS))
        pay = q("INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at) "
                "VALUES ('captured', %s, %s, '2026-08-20T10:00:00Z', '2026-08-20T10:00:01Z', '2026-08-20T10:00:02Z') RETURNING id",
                (TOTAL, uuid.uuid4().hex))
        b = q("INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) "
              "VALUES (%s, %s, %s, %s, %s, 'confirmed') RETURNING id", (reference, uid, st, pay, TOTAL))
        for num in (9, 7, 8):  # inserted out of order on purpose (P-TKT-06 step 3)
            seat = q("INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
                     "VALUES (%s, 'F', %s, 6, %s, %s) RETURNING id", (screen, num, num, premium))
            conn.execute("INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (%s, %s)", (st, seat))
            conn.execute("INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
                         "uplift_basis_points_applied, seat_category_id) VALUES (%s, %s, %s, 28124, 24999, 1250, %s)",
                         (b, st, seat, premium))
        if dispatch is not None:
            conn.execute("INSERT INTO receipt_dispatch (booking_id, status, dispatch_seq, attempts) VALUES (%s, %s, 1, 0)", (b, dispatch))
    return b


def dispatch_row(db, booking_id: int) -> tuple:
    return owner_sql(db, "SELECT status, attempts, sent_at, ses_message_id, last_error FROM receipt_dispatch WHERE booking_id = %s",
                     (booking_id,))[0]


def set_claim(db, booking_id: int, status: str, claimed_at: datetime | None = None, seq: int = 1) -> None:
    owner_sql(db, "UPDATE receipt_dispatch SET status = %s, claimed_at = %s, dispatch_seq = %s, attempts = attempts + %s "
                  "WHERE booking_id = %s", (status, claimed_at, seq, 1 if claimed_at else 0, booking_id))


def reset_token(db, user_id: int, clock: FakeClock, **cols) -> int:
    created = clock.now()
    values = {"user_id": user_id, "token_sha256": uuid.uuid4().hex * 2, "expires_at": created + timedelta(seconds=1800),
              "created_at": created, **cols}
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    return owner_sql(db, f"INSERT INTO password_reset_token ({names}) VALUES ({marks}) RETURNING id", tuple(values.values()))[0][0]

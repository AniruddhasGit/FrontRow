"""Fixtures for the booking lane (tests/pay/ S-PAY-03..15, tests/tkt/ S-TKT-01, the Phase 4 S-ACC / S-SCP rows).

The real application on a throwaway migrated database (tests/dbkit.py), connected as frontrow_app, with an
injected clock. Every HTTP call goes through httpx's ASGI transport on the test's own event loop.

REDIS. Database 11 of the compose Redis: 15 is FLUSHDB'd by other lanes, 14 / 13 / 12 belong to the admin, browse
and seat lanes. Each world flushes 11 first. The application's client is wrapped so every command it sends is
recorded in order (the "Redis command log").

PORTS. The confirm reads three optional ports from app.state (app/api/bookings.py): `payment_sleep` (the simulated
provider's artificial delay), `confirm_observer` (called with each step's name, in order) and `receipt_queue` (the
bounded post-commit send). The kit installs a recording sleep that never sleeps, so no test spends real time.

THE FIXTURE WORLD (the PRD's own figures). Showtime 7 on "Hall 2", base 27500 paise. Row F is Premium at 1250 bp
(27500 -> 30938), row J is Recliner at 3333 bp (27500 -> 36666), row C is Standard at 0 bp. Seat ids: F7 402,
F8 403, F9 404, J3 405, J4 406, C1 410, C2 411, C3 412. The five-seat selection F7 F8 F9 J3 J4 totals
3 x 30938 + 2 x 36666 = 166146.
"""

from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import event

from app.core.security import SESSION_COOKIE, issue_session_token
from app.db import make_engine
from app.main import create_app
from tests.brw.kit import SetClock, StatementCounter, make_category, make_cinema, make_movie, one
from tests.dbkit import FAKE_HASH, app_settings, owner_sql
from tests.test_health import ok_probe

SHOWTIME = 7
STARTS = "2026-08-14T20:00:00+05:30"  # 14:30Z
T0 = "2026-08-14T14:00:00+00:00"
F7, F8, F9, J3, J4, C1, C2, C3 = 402, 403, 404, 405, 406, 410, 411, 412
FIVE = [F7, F8, F9, J3, J4]
KEY = "9f2c1d4e-7b83-4a16-9c05-2e6f8a31b7d0"


def redis_url() -> str:
    base = os.environ.get("TEST_REDIS_URL")
    if not base:
        pytest.fail("TEST_REDIS_URL is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return re.sub(r"/\d+$", "/11", base)


def redis_sync():
    import redis

    return redis.Redis.from_url(redis_url(), decode_responses=True)


def r_call(*args):
    r = redis_sync()
    try:
        return r.execute_command(*args)
    finally:
        r.close()


def flush() -> None:
    r_call("FLUSHDB")


class CommandLog:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def wrap(self, client) -> None:
        original = client.execute_command

        async def recording(*args, **options):
            self.commands.append(tuple(str(a) for a in args))
            return await original(*args, **options)

        client.execute_command = recording

    def reset(self) -> None:
        self.commands.clear()


class Sleep:
    """The simulated provider's delay port: records each call, never sleeps unless a test hands it a gate."""

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.gate = None  # an asyncio.Event a test may set to hold a confirm inside its capture

    async def __call__(self, ms: int) -> None:
        self.calls.append(ms)
        if self.gate is not None:
            self.entered.set()
            await self.gate.wait()

    def hold(self):
        import asyncio

        self.gate, self.entered = asyncio.Event(), asyncio.Event()
        return self.gate, self.entered


@asynccontextmanager
async def api(db, clock, client_addr: tuple[str, int] = ("127.0.0.1", 50000), **overrides: str):
    settings = app_settings(db, **{"REDIS_URL": redis_url(), "LISTING_CACHE_TTL_SECONDS": "0", "SEATMAP_CACHE_TTL_SECONDS": "0",
                                   "PAYMENT_SIMULATOR_FAIL_KEY_PREFIX": "FAIL_", **overrides})
    engine = make_engine(settings)
    statements = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", statements)
    application = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")], engine=engine)
    try:
        async with application.router.lifespan_context(application):
            log = CommandLog()
            log.wrap(application.state.redis)
            sleep = Sleep()
            application.state.payment_sleep = sleep
            transport = httpx.ASGITransport(app=application, client=client_addr)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                client.application = application  # type: ignore[attr-defined]
                client.statements = statements  # type: ignore[attr-defined]
                client.redis_log = log  # type: ignore[attr-defined]
                client.settings = settings  # type: ignore[attr-defined]
                client.clock = clock  # type: ignore[attr-defined]
                client.sleep = sleep  # type: ignore[attr-defined]
                yield client
    finally:
        await engine.dispose()


def clock_at(instant: str = T0) -> SetClock:
    c = SetClock()
    c.set(instant)
    return c


def user(db, role: str = "customer", email: str | None = None) -> int:
    return one(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, %s, 1) RETURNING id",
               (email or f"{uuid.uuid4().hex[:10]}@example.invalid", FAKE_HASH, role))


def cookies(client, user_id: int, role: str = "customer") -> dict[str, str]:
    token = issue_session_token(user_id=user_id, role=role, password_version=1, now=client.clock.now(), settings=client.settings)
    return {SESSION_COOKIE: token}


def reset(db) -> None:
    owner_sql(db, "TRUNCATE outbox_message, receipt_dispatch, idempotency_record, booking_seat, booking, payment, audit_log, "
                  "showtime_seat, showtime, movie_genre, movie, seat, screen, cinema, seat_category, language, certification, "
                  "genre, format, users RESTART IDENTITY CASCADE")


def _seat(db, screen_id: int, seat_id: int, row: str, num: int, gr: int, category_id: int) -> None:
    owner_sql(db, "INSERT INTO seat (id, screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
                  "OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s, %s, %s)", (seat_id, screen_id, row, num, gr, num, category_id))


def showtime(db, movie_id: int, screen_id: int, showtime_id: int, starts: str = STARTS, base: int = 27500,
             ends: str | None = None) -> int:
    ends_sql = "%s::timestamptz" if ends else "%s::timestamptz + interval '2 hours'"
    owner_sql(db, "INSERT INTO showtime (id, movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version) "
                  f"OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, {ends_sql}, %s, 0, 1)",
              (showtime_id, movie_id, screen_id, starts, ends or starts, base))
    owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT %s, id FROM seat WHERE screen_id = %s AND is_active",
              (showtime_id, screen_id))
    owner_sql(db, "UPDATE showtime SET seat_count_at_creation = (SELECT count(*) FROM showtime_seat WHERE showtime_id = %s) WHERE id = %s",
              (showtime_id, showtime_id))
    return showtime_id


def world7(db, *, base: int = 27500, starts: str = STARTS, title: str = "The Long Night", timezone: str = "Asia/Kolkata") -> dict:
    reset(db)
    flush()
    cinema = make_cinema(db, timezone)
    screen = one(db, "INSERT INTO screen (id, cinema_id, name, version) OVERRIDING SYSTEM VALUE VALUES (2, %s, 'Hall 2', 1) RETURNING id",
                 (cinema,))
    standard, premium, recliner = make_category(db, 0, "Standard"), make_category(db, 1250, "Premium"), make_category(db, 3333, "Recliner")
    for sid, row, num, gr, cat in [(F7, "F", 7, 6, premium), (F8, "F", 8, 6, premium), (F9, "F", 9, 6, premium),
                                   (J3, "J", 3, 10, recliner), (J4, "J", 4, 10, recliner),
                                   (C1, "C", 1, 3, standard), (C2, "C", 2, 3, standard), (C3, "C", 3, 3, standard)]:
        _seat(db, screen, sid, row, num, gr, cat)
    movie = make_movie(db, title=title)
    showtime(db, movie, screen, SHOWTIME, starts, base)
    return {"db": db, "cinema": cinema, "screen": screen, "movie": movie, "standard": standard, "premium": premium,
            "recliner": recliner}


async def hold(client, user_id: int, seat_ids: list[int], showtime_id: int = SHOWTIME) -> dict:
    r = await client.post(f"/api/showtimes/{showtime_id}/holds", json={"seat_ids": seat_ids}, cookies=cookies(client, user_id))
    assert r.status_code == 201, r.text
    return r.json()


async def confirm(client, user_id: int, token: str, key: str | None = KEY, showtime_id: int = SHOWTIME, body: dict | None = None,
                  headers: dict | None = None):
    h = dict(headers or {})
    if key is not None:
        h["Idempotency-Key"] = key
    payload = body if body is not None else {"hold_token": token, "showtime_id": showtime_id}
    return await client.post("/api/bookings", json=payload, headers=h, cookies=cookies(client, user_id))


def count(db, sql: str, params=None) -> int:
    return owner_sql(db, sql, params)[0][0]


def book(db, user_id: int, showtime_id: int, seat_ids: list[int], *, created_at: str = "2026-08-12T10:00:00Z",
         prices: list[int] | None = None) -> tuple[int, str]:
    """A committed booking written directly (the state a read test starts from): one captured payment, the booking under
    a fresh valid reference, one booking_seat per seat in the order given. Returns (booking id, presentation reference)."""
    import psycopg

    from app.domain.reference import new_reference

    prices = prices or [25000] * len(seat_ids)
    ref = new_reference()
    with psycopg.connect(db.owner_url) as conn, conn.transaction():
        pay = conn.execute("INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at) "
                           "VALUES ('captured', %s, %s, %s, %s, %s) RETURNING id",
                           (sum(prices), uuid.uuid4().hex, created_at, created_at, created_at)).fetchone()[0]
        b = conn.execute("INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status, created_at) "
                         "VALUES (%s, %s, %s, %s, %s, 'confirmed', %s) RETURNING id",
                         (ref, user_id, showtime_id, pay, sum(prices), created_at)).fetchone()[0]
        for sid, price in zip(seat_ids, prices):
            conn.execute("INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
                         "uplift_basis_points_applied, seat_category_id) SELECT %s, %s, id, %s, %s, 0, seat_category_id FROM seat "
                         "WHERE id = %s", (b, showtime_id, price, price, sid))
    return b, f"FR-{ref[:4]}-{ref[4:]}"


def add_seats(db, screen_id: int, category_id: int, rows: list[tuple[int, str, int]], showtime_ids: list[int]) -> None:
    """Seats (id, row, number) added to a screen and to the named showtimes' seat sets."""
    for sid, row, num in rows:
        _seat(db, screen_id, sid, row, num, ord(row) - 64, category_id)
        for st in showtime_ids:
            owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (%s, %s)", (st, sid))


def movie_and_showtime(db, w: dict, showtime_id: int, starts: str, ends: str | None = None) -> int:
    """Another showtime of the world's film in the world's hall."""
    return showtime(db, w["movie"], w["screen"], showtime_id, starts, ends=ends)

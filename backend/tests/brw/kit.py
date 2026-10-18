"""Fixtures and row builders for the browse lane (tests/brw/, tests/sea/, the Phase 3 S-SCP / S-XCT / S-PAY rows).

A real app on a throwaway migrated database (tests/dbkit.py), connected as frontrow_app, with an injected
clock that a test puts at an exact instant. Every HTTP call goes through httpx's ASGI transport on the
test's own event loop, so five concurrent callers really are concurrent.

REDIS. The browse tests use database 13 of the compose Redis, not TEST_REDIS_URL's 15: other lanes FLUSHDB 15
at the start of each test, and showtime ids start at 1 in every throwaway database, so a shared database would
serve one module's cached seat map to another. Each test here flushes 13 first.

Fixture rows are written as the OWNER, directly: they are the state a test starts from, not what it proves.
Names are demonstration values; nothing here is the seed's ASSUMED vocabulary (OPEN-SEAT-01).
"""

from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import event

from app.db import make_engine
from app.main import create_app
from tests.conftest import FakeClock
from tests.dbkit import FAKE_HASH, app_settings, owner_sql
from tests.test_health import ok_probe


class SetClock(FakeClock):
    """A FakeClock a test can put at an exact instant."""

    def set(self, instant: str | datetime) -> None:
        when = datetime.fromisoformat(instant) if isinstance(instant, str) else instant
        self._mono += max(0.0, (when - self._now).total_seconds())
        self._now = when


def redis_url() -> str:
    base = os.environ.get("TEST_REDIS_URL")
    if not base:
        pytest.fail("TEST_REDIS_URL is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return re.sub(r"/\d+$", "/13", base)


def redis_sync():
    import redis

    return redis.Redis.from_url(redis_url())


def flush_redis() -> None:
    client = redis_sync()
    try:
        client.flushdb()
    finally:
        client.close()


class StatementCounter:
    """Every SQL statement the application's engine sends, in order."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def __call__(self, conn, cursor, statement, parameters, context, executemany) -> None:
        self.statements.append(statement)

    def reset(self) -> None:
        self.statements.clear()

    def matching(self, text: str) -> int:
        return sum(1 for s in self.statements if text in s)


def settings_for(db, **overrides: str):
    # TTLs of 0 switch the caches off, so a test about a query sees the query; the cache tests set them back.
    return app_settings(db, **{"REDIS_URL": redis_url(), "LISTING_CACHE_TTL_SECONDS": "0",
                               "SEATMAP_CACHE_TTL_SECONDS": "0", **overrides})


@asynccontextmanager
async def api(db, clock, client_addr: tuple[str, int] = ("127.0.0.1", 50000), **overrides: str):
    """The real application with its lifespan running, an httpx client bound to it, and a statement counter."""
    settings = settings_for(db, **overrides)
    engine = make_engine(settings)
    counter = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    application = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")], engine=engine)
    try:
        async with application.router.lifespan_context(application):
            transport = httpx.ASGITransport(app=application, client=client_addr)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                client.application = application  # type: ignore[attr-defined]
                client.statements = counter  # type: ignore[attr-defined]
                yield client
    finally:
        await engine.dispose()


def without_request_id(body: dict) -> dict:
    error = dict(body["error"])
    error.pop("request_id")
    return {**body, "error": error}


# ---- row builders ---------------------------------------------------------------------------------------


def tag() -> str:
    return uuid.uuid4().hex[:8]


def one(db, statement: str, params=None):
    return owner_sql(db, statement, params)[0][0]


def make_cinema(db, timezone: str = "Asia/Kolkata", name: str | None = None) -> int:
    return one(db, "INSERT INTO cinema (name, timezone, version) VALUES (%s, %s, 1) RETURNING id", (name or f"Venue {tag()}", timezone))


def make_screen(db, cinema_id: int, name: str | None = None) -> int:
    return one(db, "INSERT INTO screen (cinema_id, name, version) VALUES (%s, %s, 1) RETURNING id", (cinema_id, name or f"Hall {tag()}"))


def make_category(db, uplift: int = 0, name: str | None = None) -> int:
    return one(db, "INSERT INTO seat_category (name, uplift_basis_points, version) VALUES (%s, %s, 1) RETURNING id",
               (name or f"Cat {tag()}", uplift))


def make_lookup(db, table: str, name: str | None = None, active: bool = True) -> int:
    assert table in ("language", "certification", "genre", "format")
    return one(db, f"INSERT INTO {table} (name, is_active) VALUES (%s, %s) RETURNING id", (name or f"{table} {tag()}", active))


def make_seat(db, screen_id: int, row: str, num: int, gr: int, gc: int, category_id: int, active: bool = True) -> int:
    return one(db, "INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id, is_active) "
                   "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", (screen_id, row, num, gr, gc, category_id, active))


def make_movie(db, *, title: str | None = None, published_at: str | None = "2026-08-10T11:04:22+05:30",
               display_from: str | None = "2026-08-14T00:00:00+05:30", display_until: str | None = "2026-08-21T00:00:00+05:30",
               language_id: int | None = None, certification_id: int | None = None, synopsis: str = "Demonstration film.",
               runtime: int = 125, movie_id: int | None = None, poster_key: str | None = None) -> int:
    language_id = language_id or make_lookup(db, "language")
    certification_id = certification_id or make_lookup(db, "certification")
    cols = ("title, synopsis, runtime_minutes, certification_id, language_id, published_at, display_from, display_until, "
            "poster_object_key, version")
    vals = (title or f"DEMO MOVIE {tag()}", synopsis, runtime, certification_id, language_id, published_at, display_from,
            display_until, poster_key)
    if movie_id is None:
        return one(db, f"INSERT INTO movie ({cols}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1) RETURNING id", vals)
    return one(db, f"INSERT INTO movie (id, {cols}) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1) "
                   "RETURNING id", (movie_id, *vals))


def make_showtime(db, movie_id: int, screen_id: int, starts: str, ends: str | None = None, price: int = 25000,
                  format_id: int | None = None, showtime_id: int | None = None, seat_set: bool = True) -> int:
    """A stored showtime with its seat set written the way the product writes it: the hall's in-service seats now."""
    ends = ends or (datetime.fromisoformat(starts) + timedelta(hours=2)).isoformat()
    cols = "movie_id, screen_id, starts_at, ends_at, base_price_paise, format_id, seat_count_at_creation, version"
    vals = (movie_id, screen_id, starts, ends, price, format_id)
    if showtime_id is None:
        st = one(db, f"INSERT INTO showtime ({cols}) VALUES (%s, %s, %s, %s, %s, %s, 0, 1) RETURNING id", vals)
    else:
        st = one(db, f"INSERT INTO showtime (id, {cols}) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 1) "
                     "RETURNING id", (showtime_id, *vals))
    if seat_set:
        owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT %s, id FROM seat WHERE screen_id = %s AND is_active",
                  (st, screen_id))
        owner_sql(db, "UPDATE showtime SET seat_count_at_creation = (SELECT count(*) FROM showtime_seat WHERE showtime_id = %s) "
                      "WHERE id = %s", (st, st))
    return st


def make_hall(db, cinema_id: int, rows: int, cols: int, categories: list, aisle_cols: tuple[int, ...] = (),
              void_rows: tuple[int, ...] = ()) -> dict:
    """A rows x cols grid of seats. Seated grid rows take letters A.. in order (I skipped); a grid row in void_rows
    holds no seat (a cross-aisle) and takes no letter; a column in aisle_cols holds no seat, so seat numbers and
    grid columns diverge after it. categories[gr-1] is grid row gr's category id, or a list of one id per seat."""
    screen_id = make_screen(db, cinema_id)
    letters = iter("ABCDEFGHJKLMNOPQRSTUVWXYZ")
    seats: dict[str, int] = {}
    values = []
    for gr in range(1, rows + 1):
        if gr in void_rows:
            continue
        letter, num = next(letters), 0
        for gc in range(1, cols + 1):
            if gc in aisle_cols:
                continue
            num += 1
            cat = categories[gr - 1]
            values.append((screen_id, letter, num, gr, gc, cat[num - 1] if isinstance(cat, list) else cat))
    import psycopg

    with psycopg.connect(db.owner_url) as conn, conn.cursor() as cur:
        for v in values:
            cur.execute("INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", v)
            seats[f"{v[1]}-{v[2]}"] = cur.fetchone()[0]
    return {"screen_id": screen_id, "seats": seats}


def book_seat(db, showtime_id: int, seat_id: int, price: int = 25000) -> int:
    """One captured payment, one booking, one booked seat, in one transaction (the sold state's only source)."""
    import psycopg

    from app.domain.reference import new_reference

    user = one(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, 'customer', 1) RETURNING id",
               (f"{tag()}@example.invalid", FAKE_HASH))
    category = one(db, "SELECT seat_category_id FROM seat WHERE id = %s", (seat_id,))
    with psycopg.connect(db.owner_url) as conn, conn.transaction():
        payment = conn.execute("INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at) "
                               "VALUES ('captured', %s, %s, '2026-08-12T18:41:00Z', '2026-08-12T18:41:01Z', '2026-08-12T18:41:02Z') "
                               "RETURNING id", (price, uuid.uuid4().hex)).fetchone()[0]
        booking = conn.execute("INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) "
                               "VALUES (%s, %s, %s, %s, %s, 'confirmed') RETURNING id",
                               (new_reference(), user, showtime_id, payment, price)).fetchone()[0]
        conn.execute("INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
                     "uplift_basis_points_applied, seat_category_id) VALUES (%s, %s, %s, %s, %s, 0, %s)",
                     (booking, showtime_id, seat_id, price, price, category))
    return booking


def reset_catalogue(db) -> None:
    """Empty every browse table, so a module's tests do not see each other's films."""
    owner_sql(db, "TRUNCATE booking_seat, booking, payment, showtime_seat, showtime, movie_genre, movie, seat, screen, cinema, "
                  "seat_category, language, certification, genre, format, users RESTART IDENTITY CASCADE")

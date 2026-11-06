"""Fixtures and row builders for the reporting-lane tests (tests/rpt/, E7).

A real app on a throwaway migrated database (tests/dbkit.py), connected as frontrow_app, with a clock pinned at the
PRD's worked-example instant 2026-08-14T12:50:00Z (Friday 18:20 in Asia/Kolkata). Fixture rows are written as the
OWNER, directly, with explicit ids so the PRD's ST-101 / screen 3 numbering carries over verbatim. Names are
demonstration values only (OPEN-SEED-01, OPEN-SEAT-01).

REDIS. Database 10 of the compose Redis (acc 15, adm 14, brw 13, sea 12, pay 11): the reports bucket lives there,
and every client fixture starts it empty.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.security import SESSION_COOKIE, issue_session_token
from app.domain.reference import new_reference
from app.main import create_app
from tests.conftest import FakeClock
from tests.dbkit import FAKE_HASH, app_settings, owner_sql, run_sql
from tests.test_health import ok_probe

T0 = datetime(2026, 8, 14, 12, 50, tzinfo=timezone.utc)
DAY = "/api/reports/dashboard?period=day&date=2026-08-14"
INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class PinnedClock(FakeClock):
    def __init__(self, at: datetime = T0) -> None:
        super().__init__()
        self._now = at


def redis_url() -> str:
    base = os.environ.get("TEST_REDIS_URL")
    if not base:
        pytest.fail("TEST_REDIS_URL is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return re.sub(r"/\d+$", "/10", base)


def redis_sync():
    import redis

    return redis.Redis.from_url(redis_url())


def settings(db, **overrides: str):
    return app_settings(db, **{"REDIS_URL": redis_url(), **overrides})


def make_client(db, clock=None, **overrides: str) -> TestClient:
    r = redis_sync()
    r.flushdb()
    r.close()
    application = create_app(settings(db, **overrides), clock=clock or PinnedClock(),
                             probes=[ok_probe("postgres"), ok_probe("redis")])
    c = TestClient(application, raise_server_exceptions=False)
    c.db = db
    return c


@pytest.fixture
def client(world):
    with make_client(world["db"]) as c:
        c.clock = c.app.state.clock
        yield c


def get(client, user: int | None, url: str, **kw):
    """One GET as `user` (an id from `user_row`), or with no session when user is None."""
    client.cookies.clear()
    if user is not None:
        role = owner_sql(client.db, "SELECT role FROM users WHERE id = %s", (user,))[0][0]
        token = issue_session_token(user_id=user, role=role, password_version=1, now=client.app.state.clock.now(),
                                    settings=settings(client.db))
        client.cookies.set(SESSION_COOKIE, token)
    return client.get(url, **kw)


def strip_rid(body: dict) -> dict:
    body["error"].pop("request_id")
    return body


# ---- rows ----------------------------------------------------------------------------------------------------------

def one(db, sql: str, params=None):
    return owner_sql(db, sql, params)[0][0]


def bump(db, table: str) -> None:
    """An explicit id (OVERRIDING SYSTEM VALUE) does not move the identity; move it past the highest id."""
    owner_sql(db, f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")


def user_row(db, role: str, user_id: int | None = None, email: str | None = None) -> int:
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@example.invalid"
    if user_id is None:
        return one(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, %s, 1) RETURNING id",
                   (email, FAKE_HASH, role))
    uid = one(db, "INSERT INTO users (id, email, password_hash, role, password_version) OVERRIDING SYSTEM VALUE "
                   "VALUES (%s, %s, %s, %s, 1) RETURNING id", (user_id, email, FAKE_HASH, role))
    bump(db, "users")
    return uid


def assign(db, manager: int, *screens: int) -> None:
    for s in screens:
        owner_sql(db, "INSERT INTO manager_screen_assignment (user_id, screen_id) VALUES (%s, %s)", (manager, s))


def venue(db, halls: dict[int, int], premium: dict[int, int] | None = None, zone: str = "Asia/Kolkata") -> dict:
    """Cinema 1, halls {screen_id: seat count} named 'Hall <id>', two categories (0 and 3333 basis points). The last
    premium[screen_id] seats of a hall are in the second category."""
    one(db, "INSERT INTO cinema (id, name, timezone, version) OVERRIDING SYSTEM VALUE VALUES (1, 'Demo Venue', %s, 1) "
            "RETURNING id", (zone,))
    bump(db, "cinema")
    std = one(db, "INSERT INTO seat_category (name, uplift_basis_points, version) VALUES ('Cat A', 0, 1) RETURNING id")
    prem = one(db, "INSERT INTO seat_category (name, uplift_basis_points, version) VALUES ('Cat B', 3333, 1) RETURNING id")
    for sid, n in halls.items():
        owner_sql(db, "INSERT INTO screen (id, cinema_id, name, version) OVERRIDING SYSTEM VALUE VALUES (%s, 1, %s, 1)",
                  (sid, f"Hall {sid}"))
        bump(db, "screen")
        p = (premium or {}).get(sid, 0)
        owner_sql(db, "INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
                      "SELECT %s, 'R' || (g / 30), g %% 30 + 1, g / 30 + 1, g %% 30 + 1, "
                      "CASE WHEN g >= %s THEN %s ELSE %s END FROM generate_series(0, %s - 1) g",
                  (sid, n - p, prem, std, n))
    cert = one(db, "INSERT INTO certification (name, is_active) VALUES ('Cert Demo', true) RETURNING id")
    lang = one(db, "INSERT INTO language (name, is_active) VALUES ('Lang Demo', true) RETURNING id")
    return {"db": db, "std": std, "prem": prem, "cert": cert, "lang": lang}


def film(w: dict, title: str, movie_id: int | None = None) -> int:
    cols = "title, synopsis, runtime_minutes, certification_id, language_id, version"
    if movie_id is None:
        return one(w["db"], f"INSERT INTO movie ({cols}) VALUES (%s, 'Demonstration film.', 120, %s, %s, 1) RETURNING id",
                   (title, w["cert"], w["lang"]))
    mid = one(w["db"], f"INSERT INTO movie (id, {cols}) OVERRIDING SYSTEM VALUE VALUES (%s, %s, 'Demonstration film.', "
                        "120, %s, %s, 1) RETURNING id", (movie_id, title, w["cert"], w["lang"]))
    bump(w["db"], "movie")
    return mid


def show(w: dict, showtime_id: int | None, screen_id: int, movie_id: int, starts: str, base: int = 25000) -> int:
    """A showtime whose seat set is every in-service seat of its hall, written the way the product writes it."""
    db = w["db"]
    cols = "movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version"
    vals = ("%s, %s, %s::timestamptz, %s::timestamptz + interval '2 hours', %s, "
            "(SELECT count(*) FROM seat WHERE screen_id = %s AND is_active), 1")
    params = (movie_id, screen_id, starts, starts, base, screen_id)
    if showtime_id is None:
        st = one(db, f"INSERT INTO showtime ({cols}) VALUES ({vals}) RETURNING id", params)
    else:
        st = one(db, f"INSERT INTO showtime (id, {cols}) OVERRIDING SYSTEM VALUE VALUES (%s, {vals}) RETURNING id",
                 (showtime_id, *params))
        bump(db, "showtime")
    owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT %s, id FROM seat WHERE screen_id = %s AND is_active",
              (st, screen_id))
    return st


def sell(w: dict, showtime_id: int, n: int, price: int, *, premium: bool = False, state: str = "captured",
         per_booking: int = 10, user: int | None = None) -> list[int]:
    """n unsold seats of the showtime (of the chosen category) on bookings of up to `per_booking` seats each, each
    with its own payment in `state`. Returns the booking ids."""
    db = w["db"]
    customer = user or user_row(db, "customer")
    category = w["prem"] if premium else w["std"]
    seats = [r[0] for r in owner_sql(db, """
        SELECT ss.seat_id FROM showtime_seat ss JOIN seat s ON s.id = ss.seat_id
        WHERE ss.showtime_id = %s AND s.seat_category_id = %s
          AND NOT EXISTS (SELECT 1 FROM booking_seat bs WHERE bs.showtime_id = ss.showtime_id AND bs.seat_id = ss.seat_id)
        ORDER BY ss.seat_id LIMIT %s""", (showtime_id, category, n))]
    assert len(seats) == n, f"only {len(seats)} unsold seats of that category on showtime {showtime_id}"
    uplift = 3333 if premium else 0
    bookings = []
    with psycopg.connect(db.owner_url) as conn, conn.transaction():
        for i in range(0, n, per_booking):
            chunk = seats[i:i + per_booking]
            total = price * len(chunk)
            captured = state == "captured"
            payment = conn.execute(
                "INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at) "
                "VALUES (%s, %s, %s, '2026-08-12T10:00:00Z', %s, %s) RETURNING id",
                (state, total, uuid.uuid4().hex, "2026-08-12T10:00:01Z" if captured else None,
                 "2026-08-12T10:00:02Z" if captured else None)).fetchone()[0]
            booking = conn.execute(
                "INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) "
                "VALUES (%s, %s, %s, %s, %s, 'confirmed') RETURNING id",
                (new_reference(), customer, showtime_id, payment, total)).fetchone()[0]
            for seat in chunk:
                conn.execute("INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
                             "uplift_basis_points_applied, seat_category_id) VALUES (%s, %s, %s, %s, 25000, %s, %s)",
                             (booking, showtime_id, seat, price, uplift, category))
            bookings.append(booking)
    return bookings


def takings_sql(db, screens: tuple[int, ...], lo: str = "2026-08-13T18:30:00Z", hi: str = "2026-08-14T18:30:00Z") -> int:
    """The AC's own reference query, run by the test - so a constant and the query check one another."""
    return one(db, "SELECT COALESCE(SUM(bs.price_paise),0) FROM booking_seat bs JOIN booking b ON bs.booking_id=b.id "
                   "JOIN payment p ON p.id=b.payment_id JOIN showtime st ON st.id=b.showtime_id "
                   "WHERE st.screen_id = ANY(%s) AND st.starts_at >= %s AND st.starts_at < %s "
                   "AND b.status='confirmed' AND p.state='captured'", (list(screens), lo, hi))


def prd_world(db) -> dict:
    """P-RPT-03/04/05's worked example (S-RPT-06's seed). Hall sizes ASSUMED (OPEN-SCALE-02): 3 -> 150, 5 -> 220."""
    w = venue(db, {1: 40, 2: 30, 3: 150, 4: 30, 5: 220, 6: 30}, premium={3: 10})
    w["m01"], w["m02"] = film(w, "DEMO MOVIE 01", 1), film(w, "DEMO MOVIE 02", 2)
    show(w, 101, 3, 1, "2026-08-14T14:00:00Z")
    show(w, 102, 5, 1, "2026-08-14T18:15:00Z")
    show(w, 103, 1, 2, "2026-08-14T14:00:00Z")
    show(w, 104, 3, 1, "2026-08-14T19:00:00Z")
    sell(w, 101, 90, 25000)
    sell(w, 101, 7, 33333, premium=True)
    sell(w, 101, 3, 25000, state="failed")  # a failed payment: contributes nothing
    sell(w, 102, 12, 25000)
    sell(w, 103, 5, 25000)  # outside M's scope
    sell(w, 104, 40, 25000)  # Saturday local: outside the Friday window
    w["admin"] = user_row(db, "admin")
    w["M"] = user_row(db, "manager")
    assign(db, w["M"], 3, 5)
    w["P"] = user_row(db, "manager")  # no assignment
    w["customer"] = user_row(db, "customer")
    return w


class ServerLog:
    """What the server itself logs for the app's connections: log_statement=all, delivered to the client as LOG
    notices (client_min_messages=log), captured by a notice handler on every pooled connection. This is the server's
    statement log, BEGIN included - not the driver's view of what it sent."""

    def __init__(self, db) -> None:
        self.lines: list[str] = []
        run_sql(db.admin_url, f'ALTER DATABASE "{db.name}" SET log_statement = \'all\'')
        run_sql(db.admin_url, f'ALTER DATABASE "{db.name}" SET client_min_messages = \'log\'')

    def attach(self, client) -> None:
        from sqlalchemy import event

        def on_connect(dbapi_conn, _record):
            dbapi_conn.driver_connection.add_notice_handler(lambda d: self.lines.append(d.message_primary or ""))

        event.listen(client.app.state.db_engine.sync_engine, "connect", on_connect)

    def statements(self) -> list[str]:
        return [ln.removeprefix("statement: ") for ln in self.lines if ln.startswith("statement: ")]

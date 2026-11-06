"""Fixtures for the seat-hold lane (tests/sea/ S-SEA-05..21, the Phase 4 S-XCT / S-ADM rows).

The real application on a throwaway migrated database (tests/dbkit.py), connected as frontrow_app, with an
injected clock. Every HTTP call goes through httpx's ASGI transport on the test's own event loop.

REDIS. Database 12 of the compose Redis - not 15 (other lanes FLUSHDB it) and not 13 (the browse lane's). Each
test flushes 12 first. The application's own client is wrapped so every command it sends is recorded IN ORDER:
that is the "Redis command log" the criteria assert against (SET NX PX, never SETNX/EXPIRE; DEL cache after
the lock writes; no SCAN/KEYS on the cap path). It records what the application sent, not what Redis did.

THE FIXTURE WORLD (S-SEA-06's): showtime 77 on screen 3, seat id 4NN is row C seat NN, so 402 is C2 and 412 is
C12. Categories Standard 0 bp, Premium 1250 bp, Recliner 3333 bp. Base price 25000 paise.
"""

from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager, contextmanager

import httpx
import pytest
from sqlalchemy import event

from app.core.security import SESSION_COOKIE, issue_session_token
from app.db import make_engine
from app.main import create_app
from tests.brw.kit import SetClock, StatementCounter, make_category, make_cinema, make_movie, make_screen, one
from tests.dbkit import FAKE_HASH, app_settings, owner_sql
from tests.test_health import ok_probe

__all__ = ["SetClock", "api", "redis_sync", "flush", "world77", "user", "session", "owner_sql", "one", "book"]

SHOWTIME = 77
STARTS = "2026-08-14T19:30:00+05:30"
# The PRD's named instant (P-HLD-03): 2026-08-14T19:32:37.412+05:30.
T0 = "2026-08-14T14:02:37.412+00:00"


def redis_url() -> str:
    base = os.environ.get("TEST_REDIS_URL")
    if not base:
        pytest.fail("TEST_REDIS_URL is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return re.sub(r"/\d+$", "/12", base)


def redis_sync():
    import redis

    return redis.Redis.from_url(redis_url(), decode_responses=True)


def flush() -> None:
    r = redis_sync()
    try:
        r.flushdb()
    finally:
        r.close()


class CommandLog:
    """Every command the application's Redis client sent, as tuples of strings, in order."""

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

    def names(self) -> list[str]:
        return [c[0].upper() for c in self.commands]

    def of(self, name: str) -> list[tuple[str, ...]]:
        return [c for c in self.commands if c[0].upper() == name]


@asynccontextmanager
async def api(db, clock, client_addr: tuple[str, int] = ("127.0.0.1", 50000), **overrides: str):
    settings = app_settings(db, **{"REDIS_URL": redis_url(), "LISTING_CACHE_TTL_SECONDS": "0",
                                   "SEATMAP_CACHE_TTL_SECONDS": "0", **overrides})
    engine = make_engine(settings)
    statements = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", statements)
    application = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")], engine=engine)
    try:
        async with application.router.lifespan_context(application):
            log = CommandLog()
            log.wrap(application.state.redis)
            from tests.pay.kit import Sleep

            # The confirm's simulated-provider delay port: recorded, never slept (no test here spends real time).
            application.state.payment_sleep = Sleep()
            transport = httpx.ASGITransport(app=application, client=client_addr)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                client.application = application  # type: ignore[attr-defined]
                client.statements = statements  # type: ignore[attr-defined]
                client.redis_log = log  # type: ignore[attr-defined]
                client.settings = settings  # type: ignore[attr-defined]
                client.clock = clock  # type: ignore[attr-defined]
                yield client
    finally:
        await engine.dispose()


def user(db, role: str = "customer", user_id: int | None = None) -> int:
    email = f"{uuid.uuid4().hex[:10]}@example.invalid"
    if user_id is None:
        return one(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, %s, 1) RETURNING id",
                   (email, FAKE_HASH, role))
    return one(db, "INSERT INTO users (id, email, password_hash, role, password_version) OVERRIDING SYSTEM VALUE "
                   "VALUES (%s, %s, %s, %s, 1) RETURNING id", (user_id, email, FAKE_HASH, role))


def session(client, user_id: int, role: str = "customer") -> dict[str, str]:
    """The cookie a signed-in browser sends, minted with the product's own token function."""
    token = issue_session_token(user_id=user_id, role=role, password_version=1, now=client.clock.now(),
                                settings=client.settings)
    return {SESSION_COOKIE: token}


def reset(db) -> None:
    owner_sql(db, "TRUNCATE booking_seat, booking, payment, showtime_seat, showtime, movie_genre, movie, seat, screen, cinema, "
                  "seat_category, language, certification, genre, format, users RESTART IDENTITY CASCADE")


def seat(db, screen_id: int, seat_id: int, row: str, num: int, gr: int, gc: int, category_id: int, active: bool = True) -> int:
    return one(db, "INSERT INTO seat (id, screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id, is_active) "
                   "OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (seat_id, screen_id, row, num, gr, gc, category_id, active))


def showtime(db, movie_id: int, screen_id: int, showtime_id: int, starts: str = STARTS, price: int = 25000) -> int:
    """A stored showtime whose seat set is the hall's in-service seats at this moment (P-ADM-14)."""
    st = one(db, "INSERT INTO showtime (id, movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, "
                 "version) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s::timestamptz + interval '2 hours', %s, 0, 1) "
                 "RETURNING id", (showtime_id, movie_id, screen_id, starts, starts, price))
    owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT %s, id FROM seat WHERE screen_id = %s AND is_active",
              (st, screen_id))
    owner_sql(db, "UPDATE showtime SET seat_count_at_creation = (SELECT count(*) FROM showtime_seat WHERE showtime_id = %s) "
                  "WHERE id = %s", (st, st))
    return st


def world77(db, *, base: int = 25000, starts: str = STARTS, retire_412: bool = True) -> dict:
    """Screen 3, seats 401..418 and 420 (row C, seat NN = id - 400), categories by seat: 401-410 Standard,
    411-415 Premium, 416-420 Recliner. Showtime 77 and showtime 88 on it. After showtime 77 exists, seat 412 is
    taken out of service and seat 419 is added to the hall, so 412 is in 77's seat set but inactive and 419 is
    on screen 3 but not in 77's set (S-SEA-06)."""
    reset(db)
    flush()
    cinema = make_cinema(db, "Asia/Kolkata")
    screen = one(db, "INSERT INTO screen (id, cinema_id, name, version) OVERRIDING SYSTEM VALUE VALUES (3, %s, 'Hall 3', 1) "
                     "RETURNING id", (cinema,))
    standard, premium, recliner = make_category(db, 0, "Standard"), make_category(db, 1250, "Premium"), make_category(db, 3333, "Recliner")
    for n in [*range(1, 19), 20]:
        cat = standard if n <= 10 else premium if n <= 15 else recliner
        seat(db, screen, 400 + n, "C", n, 3, n, cat)
    movie = make_movie(db)
    showtime(db, movie, screen, SHOWTIME, starts, base)
    showtime(db, movie, screen, 88, starts, base)
    if retire_412:
        owner_sql(db, "UPDATE seat SET is_active = false WHERE id = 412")
    seat(db, screen, 419, "C", 19, 3, 19, standard)
    return {"db": db, "screen": screen, "movie": movie, "standard": standard, "premium": premium, "recliner": recliner}


def book(db, showtime_id: int, seat_id: int, price: int = 25000) -> int:
    from tests.brw.kit import book_seat

    return book_seat(db, showtime_id, seat_id, price)


def r_pttl(key: str) -> int:
    r = redis_sync()
    try:
        return r.pttl(key)
    finally:
        r.close()


def r_keys(pattern: str) -> list[str]:
    """`KEYS` sorted: Redis fixes no order for KEYS, so a comparison is over the sorted set (S-SEA-06)."""
    r = redis_sync()
    try:
        return sorted(r.keys(pattern))
    finally:
        r.close()


def r_call(*args):
    r = redis_sync()
    try:
        return r.execute_command(*args)
    finally:
        r.close()


async def confirm(client, user_id: int, token: str, key: str | None = None, showtime_id: int = SHOWTIME):
    """POST /api/bookings (EP-PAY-01) for a hold on showtime 77, with a fresh Idempotency-Key unless one is given."""
    from tests.pay.kit import confirm as pay_confirm

    return await pay_confirm(client, user_id, token, key or uuid.uuid4().hex, showtime_id=showtime_id)


def payments(db) -> int:
    return one(db, "SELECT count(*) FROM payment")


# ---- a REAL api process (the real boot path, uvicorn, SIGTERM) inside the test image ----------------------

LIVE_SESSION_AT = "2099-01-01T00:00:00+00:00"  # a session minted here outlives the process's real clock


@contextmanager
def live_api(db, tmp_path, **env_overrides: str):
    """tests/drain_harness.py as a subprocess on a free loopback port, against this test's database and Redis 12.
    Yields (base_url, proc). The readiness poll sleeps between tries: it waits on an external process, reads no clock
    and asserts nothing about time (the S-SEA-08 rg finds it all the same - see that row's doc defect)."""
    import socket
    import subprocess
    import sys
    import time

    from tests.conftest import VALID_ENV
    from tests.dbkit import BACKEND_DIR

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, **VALID_ENV, "DATABASE_URL": db.app_url, "REDIS_URL": redis_url(), "API_PORT": str(port),
           "SHUTDOWN_DRAIN_TIMEOUT_SECONDS": "20", "PYTHONPATH": str(BACKEND_DIR), **env_overrides}
    log_path = tmp_path / "api.log"
    out = open(log_path, "w")
    proc = subprocess.Popen([sys.executable, "-m", "tests.drain_harness"], cwd=BACKEND_DIR, env=env, stdout=out,
                            stderr=subprocess.STDOUT)
    proc.log = lambda: log_path.read_text()[-3000:]  # type: ignore[attr-defined]
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(400):
            try:
                if httpx.get(f"{base}/health/live", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert proc.poll() is None, proc.log()
            time.sleep(0.05)
        else:
            raise AssertionError("the api never answered 200 on /health/live: " + proc.log())
        yield base, proc
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        out.close()


def live_cookie(db, user_id: int, role: str = "customer") -> dict[str, str]:
    from datetime import datetime

    token = issue_session_token(user_id=user_id, role=role, password_version=1,
                                now=datetime.fromisoformat(LIVE_SESSION_AT), settings=app_settings(db))
    return {SESSION_COOKIE: token}


STRESS_PASSWORD = "stress-drill-only-" + "pw"  # local throwaway, never a seed default


def stress_customers(db, n: int) -> None:
    """customer-01@ .. customer-NN@ at the seed's domain, the addresses scripts/stress_seats.py signs in as."""
    from app.core.config import Settings
    from app.core.security import hash_password
    from tests.conftest import VALID_ENV

    hashed = hash_password(STRESS_PASSWORD, Settings(**VALID_ENV).BCRYPT_COST)
    for i in range(1, n + 1):
        owner_sql(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, 'customer', 1)",
                  (f"customer-{i:02d}@demo.frontrow.invalid", hashed))


def run_stress(base: str, db, *args: str):
    """scripts/stress_seats.py as the operator runs it, against a loopback base URL. Returns (code, outcome, stderr)."""
    import json
    import subprocess
    import sys

    from tests.xct._support import REPO

    env = {**os.environ, "STRESS_OPERATOR": "pytest p4-close lane", "SEED_DEFAULT_PASSWORD": STRESS_PASSWORD,
           "RATE_LIMIT_LOGIN_IP_PER_15MIN": "60", "RATE_LIMIT_HOLD_IP_PER_MIN": "60"}
    done = subprocess.run([sys.executable, str(REPO / "scripts/stress_seats.py"), "--base-url", base, "--database-url",
                           db.app_url, *args], env=env, capture_output=True, text=True, timeout=300)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("{")]
    return done.returncode, (json.loads(lines[-1]) if lines else None), done.stderr

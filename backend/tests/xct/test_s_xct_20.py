"""S-XCT-20: each of Redis's three jobs (holds, the rate limiter, the cache) behaves differently when Redis is gone.

HERE the application's own Redis client is pointed at a port nothing listens on (as tests/sea/test_s_sea_15.py does),
so every command is a real connection refusal through the real client and its real timeouts - no mock. Asserted: the
hold and confirm 503 sentences with no payment row written, GET /api/movies and GET /api/showtimes answering 200 from
PostgreSQL, the seat map's own 503 sentence, /health/ready 503 with checks.redis 'unreachable', the connect and
command timeouts appearing only where the client is constructed, and no lock fallback in backend/app/domain/holds/.

FAILS AS WRITTEN: "the hold path issues zero SQL statements while Redis is unreachable". It issues one: the router's
signed_in dependency reads the session's users row before the rate limiter's Redis call fails. The test pins that
one statement (no seat table, no lock); making it zero means running the limiter before authentication, which is a
design decision, not a test fix.

NOT asserted here:
- "With the Redis container stopped" and "after a Redis restart every live hold is gone and the next confirm returns
  409 HOLD_EXPIRED": stopping and restarting a sibling container is a live drill (tests/sea/drill_live.py stage
  redis-stop), which a test container cannot run.
- "every other limited endpoint returns 503 with message 'That is unavailable right now. Try again in a few minutes.'":
  the code gives each limited endpoint its own sentence (sign-in, registration, password reset, the dashboard, the
  booking lookups), which their own stories specify. The cells disagree; that clause needs a Bible amendment.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import event

from app.db import make_engine
from app.main import create_app
from tests.brw.kit import StatementCounter
from tests.dbkit import app_settings
from tests.sea.kit import T0, SetClock, one, session, user, world77
from tests.xct._support import rg

pytestmark = pytest.mark.anyio
HOLDS_DOWN = "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes."
SEATMAP_DOWN = "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes."


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


@asynccontextmanager
async def redis_gone(db):
    clock = SetClock()
    clock.set(T0)
    settings = app_settings(db, REDIS_URL="redis://redis:1/12")
    engine = make_engine(settings)
    statements = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", statements)
    app = create_app(settings, clock=clock, engine=engine)  # the real probes: Postgres SELECT 1 and Redis PING
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                c.application, c.statements, c.settings, c.clock = app, statements, settings, clock
                yield c
    finally:
        await engine.dispose()


def _err(r) -> tuple:
    e = r.json()["error"]
    assert re.fullmatch(r"[0-9a-f]{8}", e["request_id"])
    return r.status_code, e["code"], e["message"]


async def test_holds_and_confirm_fail_the_seat_map_fails_closed_and_browsing_still_works(world):
    customer = user(world["db"])
    payments = one(world["db"], "SELECT count(*) FROM payment")
    async with redis_gone(world["db"]) as c:
        cookies = session(c, customer)
        c.statements.reset()
        hold = await c.post("/api/showtimes/41/holds", json={"seat_ids": [312]}, cookies=cookies)
        hold_sql = list(c.statements.statements)
        confirm = await c.post("/api/bookings", json={"hold_token": "A" * 43, "showtime_id": 41},
                               headers={"Idempotency-Key": "k-xct20"}, cookies=cookies)
        seatmap = await c.get("/api/showtimes/41/seatmap")
        movies = await c.get("/api/movies")
        showtimes = await c.get("/api/showtimes", params={"movie_id": world["movie"]})
        ready = await c.get("/health/ready")
    assert _err(hold) == (503, "DEPENDENCY_UNAVAILABLE", HOLDS_DOWN)
    # RECORDED DEVIATION, not the cell: the cell says zero SQL statements. The hold path sends exactly ONE - the router's
    # signed_in dependency reading the session's users row, which runs before the rate limiter fails. Nothing touches a
    # seat table and nothing locks. The row stays Blocked on this clause.
    assert len(hold_sql) == 1 and hold_sql[0].lstrip().startswith("SELECT users.id"), hold_sql
    status, code, message = _err(confirm)
    assert (status, code) == (503, "DEPENDENCY_UNAVAILABLE")
    assert message == ("We cannot complete your booking right now. You have not been charged. Try again in a few minutes. "
                       f"If you need help, quote {confirm.json()['error']['request_id']}.")
    assert one(world["db"], "SELECT count(*) FROM payment") == payments
    assert _err(seatmap) == (503, "DEPENDENCY_UNAVAILABLE", SEATMAP_DOWN)
    assert movies.status_code == 200, movies.text
    assert showtimes.status_code == 200, showtimes.text
    assert ready.status_code == 503 and ready.json()["checks"]["redis"] == "unreachable"
    assert c.settings.READINESS_CACHE_TTL_SECONDS == 3


def test_both_timeouts_appear_only_where_the_client_is_constructed():
    hits = rg(r"socket_connect_timeout|socket_timeout", "backend/app")
    assert {h[0] for h in hits} == {"backend/app/main.py"}, hits
    lines = " ".join(h[2] for h in hits)
    assert "socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_MS" in lines
    assert "socket_timeout=settings.REDIS_COMMAND_TIMEOUT_MS" in lines


def test_no_postgresql_fallback_for_locking_in_the_holds_domain():
    assert rg(r"FOR UPDATE|with_for_update|advisory_lock|pg_advisory", "backend/app/domain/holds/") == []

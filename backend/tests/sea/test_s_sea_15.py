"""S-SEA-15 (P-HLD-10): with Redis unreachable the hold, the read, both releases and the confirm fail loudly - never
a fallback.

HERE the application's own client is pointed at a port nothing listens on, so every command is a real connection
refusal through the real client and its real timeouts - no mock anywhere. The criterion's other half, the Redis
CONTAINER actually stopped and then started again, is the host drill backend/tests/sea/drill_live.py (stage
`redis-stop`), because a container cannot stop a sibling container from inside the test image.

Recorded deviation: the command log of a failing request is not empty - it holds exactly ONE attempted command,
the rate limiter's EVAL, which is the command that failed. Nothing after it is sent. Not here: `boot exits non-zero
when REDIS_*_TIMEOUT_MS is absent` - config.py defaults both to 500, which the same criterion also states.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import event

from app.core.config import ConfigError, load_settings
from app.db import make_engine
from app.main import create_app
from tests.brw.kit import StatementCounter
from tests.sea.kit import CommandLog, SetClock, T0, session, user, world77
from tests.dbkit import app_settings

pytestmark = pytest.mark.anyio
DOWN = "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes."
TOKEN = "A" * 43


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


@asynccontextmanager
async def unreachable(db):
    clock = SetClock()
    clock.set(T0)
    settings = app_settings(db, REDIS_URL="redis://redis:1/12", READINESS_CACHE_TTL_SECONDS="0")
    engine = make_engine(settings)
    statements = StatementCounter()
    event.listen(engine.sync_engine, "before_cursor_execute", statements)
    app = create_app(settings, clock=clock, engine=engine)  # the REAL probes: Postgres SELECT 1 and Redis PING
    try:
        async with app.router.lifespan_context(app):
            log = CommandLog()
            log.wrap(app.state.redis)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                c.application, c.statements, c.redis_log, c.settings, c.clock = app, statements, log, settings, clock
                yield c
    finally:
        await engine.dispose()


async def test_every_hold_endpoint_answers_503_with_a_body_and_touches_no_seat_table(world):
    customer = user(world["db"])
    async with unreachable(world["db"]) as c:
        cookies = session(c, customer)
        results = []
        for method, url, body in (("POST", "/api/showtimes/77/holds", {"seat_ids": [402]}), ("GET", f"/api/holds/{TOKEN}", None),
                                  ("DELETE", f"/api/holds/{TOKEN}", None), ("DELETE", f"/api/holds/{TOKEN}/seats/402", None)):
            c.statements.reset()
            c.redis_log.reset()
            r = await c.request(method, url, json=body, cookies=cookies)
            results.append((method, url, r, list(c.statements.statements), list(c.redis_log.commands)))
        live = await c.get("/health/live")
        ready = await c.get("/health/ready")
        kwargs = c.application.state.redis.connection_pool.connection_kwargs
    for method, url, r, sql, sent in results:
        err = r.json()["error"]
        assert (r.status_code, err["code"]) == (503, "DEPENDENCY_UNAVAILABLE"), (method, url)
        assert err["message"] == DOWN and re.fullmatch(r"[0-9a-f]{8}", err["request_id"])
        assert not [s for s in sql if re.search(r"\b(seat|showtime|booking_seat|showtime_seat)\b", s) or "FOR UPDATE" in s]
        assert [cmd[0] for cmd in sent] == ["EVAL"]  # the one attempt that failed; the failure path sends nothing
    assert live.status_code == 200 and ready.status_code == 503
    assert kwargs["socket_connect_timeout"] * 1000 == c.settings.REDIS_CONNECT_TIMEOUT_MS == 500
    assert kwargs["socket_timeout"] * 1000 == c.settings.REDIS_COMMAND_TIMEOUT_MS == 500


@pytest.mark.parametrize("name", ["REDIS_CONNECT_TIMEOUT_MS", "REDIS_COMMAND_TIMEOUT_MS"])
@pytest.mark.parametrize("value", ["soon", "0", "-1"])
def test_a_timeout_that_is_not_a_positive_integer_stops_the_boot(valid_env, name, value):
    valid_env.setenv(name, value)
    with pytest.raises(ConfigError) as caught:
        load_settings()
    assert name in caught.value.names


async def test_redis_failing_after_a_seat_was_won_sends_nothing_more(world, monkeypatch):
    """P-HLD-10: Redis dies part-way through the SET NX loop, after 402 was won. The failure path sends no
    compare-and-delete for 402 (or anything else); the key expires within the hold's TTL on its own."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    from app.core import locks
    from tests.sea.kit import api, r_call

    customer = user(world["db"])
    real, calls, sent_at_failure = locks.acquire, [], []

    async def dying(redis, key, token, ttl_ms):
        calls.append(key)
        if key == "lock:seat:77:403":
            sent_at_failure.append(len(c.redis_log.commands))
            raise RedisConnectionError("Redis went away mid-request")
        return await real(redis, key, token, ttl_ms)

    clock = SetClock()
    clock.set(T0)
    async with api(world["db"], clock) as c:
        monkeypatch.setattr(locks, "acquire", dying)
        c.redis_log.reset()
        r = await c.post("/api/showtimes/77/holds", json={"seat_ids": [402, 403]}, cookies=session(c, customer))
        sent = list(c.redis_log.commands)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (503, "DEPENDENCY_UNAVAILABLE", DOWN)
    assert "lock:seat:77:402" in calls and sent_at_failure and sent[sent_at_failure[0]:] == []
    assert r_call("EXISTS", "lock:seat:77:402") == 1  # left to its own TTL, never deleted after the failure


async def test_the_confirm_answers_503_with_its_own_sentence_and_captures_nothing(world):
    from tests.sea.kit import one

    customer = user(world["db"])
    async with unreachable(world["db"]) as c:
        c.statements.reset()
        c.redis_log.reset()
        r = await c.post("/api/bookings", json={"hold_token": TOKEN, "showtime_id": 77},
                         headers={"Idempotency-Key": "k-503"}, cookies=session(c, customer))
        sql, sent = list(c.statements.statements), list(c.redis_log.commands)
    err = r.json()["error"]
    assert (r.status_code, err["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert re.fullmatch(r"[0-9a-f]{8}", err["request_id"])
    assert err["message"] == ("We cannot complete your booking right now. You have not been charged. Try again in a few "
                              f"minutes. If you need help, quote {err['request_id']}.")
    assert one(world["db"], "SELECT count(*) FROM payment") == 0  # the simulated provider recorded no attempt
    assert not [s for s in sql if re.search(r"\b(seat|showtime|booking_seat|showtime_seat)\b", s) or "FOR UPDATE" in s]
    assert [cmd[0] for cmd in sent] == ["EVAL"]


async def test_postgres_failing_mid_hold_with_redis_up_releases_the_customer_mutex(world, monkeypatch):
    """The other failure: PostgreSQL fails part-way while Redis answers. Nothing is held, and the per-customer mutex is
    released at once - the customer's next press is served, not made to poll out MUTEX_TTL_MS."""
    import app.domain.holds as holds_module
    from tests.sea.kit import api, r_keys

    async def pg_down(*args, **kwargs):
        raise RuntimeError("PostgreSQL failed part-way (test double)")

    clock = SetClock()
    clock.set(T0)
    customer = user(world["db"])
    real = holds_module._price_and_sold
    async with api(world["db"], clock) as c:
        monkeypatch.setattr(holds_module, "_price_and_sold", pg_down)
        failed = await c.post("/api/showtimes/77/holds", json={"seat_ids": [402]}, cookies=session(c, customer))
        assert failed.status_code == 500
        assert r_keys(f"{holds_module.mutex_key(customer, 77)}*") == []
        assert r_keys("lock:seat:77:*") == []
        monkeypatch.setattr(holds_module, "_price_and_sold", real)
        held = await c.post("/api/showtimes/77/holds", json={"seat_ids": [402]}, cookies=session(c, customer))
    assert held.status_code == 201, held.text

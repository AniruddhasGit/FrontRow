"""S-XCT-19 (P-XCT-08, SRC-002 §8.2): the seat map and the listings are cache-aside; invalidation is a DEL.

The Phase 4 half is at the end: the entry gone after a hold, a release and a booking; the command order from hold
to booking (SET NX -> COMMIT -> the lock's compare-and-delete -> DEL cache); a DEL that raises.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_hall, make_movie, make_showtime,
                           redis_sync, reset_catalogue)
from tests.brw.test_s_brw_16 import record
from tests.xct._support import rg

pytestmark = pytest.mark.anyio

CACHED = {"LISTING_CACHE_TTL_SECONDS": "60", "SEATMAP_CACHE_TTL_SECONDS": "10"}


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_hall(db, make_cinema(db), rows=2, cols=6, categories=[make_category(db)] * 2)
    make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30", showtime_id=41)
    return {"db": db, "seats": hall["seats"]}


async def test_a_miss_writes_the_entry_with_its_configured_ttl(world):
    async with api(world["db"], SetClock(), **CACHED) as c:
        assert (await c.get("/api/showtimes/41/seatmap")).status_code == 200
    r = redis_sync()
    try:
        assert 1 <= r.ttl("cache:seatmap:41") <= 10
    finally:
        r.close()


async def test_the_rebuild_lock_ttl_is_configuration(world):
    async with api(world["db"], SetClock(), CACHE_REBUILD_LOCK_TTL_MS="1500", **CACHED) as c:
        log = record(c)
        await c.get("/api/showtimes/41/seatmap")
    rebuild = [cmd for cmd, _ in log if cmd.startswith("SET cache:seatmap:41:rebuild")]
    assert len(rebuild) == 1 and "NX" in rebuild[0] and "PX 1500" in rebuild[0]
    assert rg("2000", "backend/app/core/cache.py") == []
    assert rg("stampede", "backend/app/core/cache.py", fixed=True)


async def test_two_concurrent_misses_agree_and_only_one_rebuilds(world):
    async with api(world["db"], SetClock(), **CACHED) as c:
        c.statements.reset()
        a, b = await asyncio.gather(c.get("/api/showtimes/41/seatmap"), c.get("/api/showtimes/41/seatmap"))
        rebuild_queries = c.statements.matching("showtime_seat")
    assert (a.status_code, b.status_code) == (200, 200)
    assert [(s["id"], s["state"]) for s in a.json()["seats"]] == [(s["id"], s["state"]) for s in b.json()["seats"]]
    assert rebuild_queries == 1


async def test_a_released_seat_is_seen_available_within_ttl_plus_poll_in_real_time(world):
    """Worst case: the release's DEL of the cache entry is lost, so only the entry's own expiry ends the staleness.
    Real elapsed time, because Redis expires keys on its own clock and the injected clock does not move it."""
    seat = world["seats"]["A-1"]
    r = redis_sync()
    r.set(f"lock:seat:41:{seat}", "someone", px=60_000)
    async with api(world["db"], SetClock(), **CACHED) as c:
        state = lambda body: next(s["state"] for s in body["seats"] if s["id"] == seat)  # noqa: E731
        assert state((await c.get("/api/showtimes/41/seatmap")).json()) == "held"
        r.delete(f"lock:seat:41:{seat}")  # released, and the cache entry NOT deleted
        released = time.perf_counter()
        while True:
            if state((await c.get("/api/showtimes/41/seatmap")).json()) == "available":
                break
            assert time.perf_counter() - released <= 13
            await asyncio.sleep(3)  # the default poll interval
    r.close()
    assert time.perf_counter() - released <= 13


# ---- Phase 4: the hold, release and booking paths invalidate with a DEL after they commit -----------------


def _pay_world(migrated_db):
    from tests.pay.kit import world7

    return world7(migrated_db)


async def test_after_a_hold_a_release_and_a_booking_the_entry_is_gone(migrated_db):
    from tests.pay.kit import C1, C2, api, clock_at, confirm, cookies, hold, r_call, user

    db = _pay_world(migrated_db)["db"]
    u = user(db)
    gone = {}
    async with api(db, clock_at(), SEATMAP_CACHE_TTL_SECONDS="10") as c:
        async def warm() -> None:
            assert (await c.get("/api/showtimes/7/seatmap")).status_code == 200
            assert r_call("EXISTS", "cache:seatmap:7") == 1

        await warm()
        h = await hold(c, u, [C1, C2])
        gone["hold"] = r_call("EXISTS", "cache:seatmap:7")
        await warm()
        assert (await c.delete(f"/api/holds/{h['hold_token']}/seats/{C2}", cookies=cookies(c, u))).status_code == 200
        gone["release"] = r_call("EXISTS", "cache:seatmap:7")
        await warm()
        assert (await confirm(c, u, h["hold_token"])).status_code == 201
        gone["booking"] = r_call("EXISTS", "cache:seatmap:7")
    assert gone == {"hold": 0, "release": 0, "booking": 0}


async def test_the_command_order_for_a_seat_from_hold_to_booking(migrated_db):
    """SET lock NX (the hold), then the booking's COMMIT, then the lock's release, then DEL cache:seatmap:7. The
    release is the compare-and-delete script (EVAL), never a bare DEL: a bare DEL could delete another holder's key."""
    from sqlalchemy import event

    from tests.pay.kit import C1, api, clock_at, confirm, hold, user

    db = _pay_world(migrated_db)["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        log = c.redis_log
        event.listen(c.application.state.db_engine.sync_engine, "commit", lambda conn: log.commands.append(("COMMIT",)))
        log.reset()
        h = await hold(c, u, [C1])
        log.reset()  # the hold's own commands are asserted below from a second, booking-only window
        r = await confirm(c, u, h["hold_token"])
        booking = list(log.commands)
    assert r.status_code == 201
    key = f"lock:seat:7:{C1}"

    def at(predicate) -> int:
        return next(i for i, cmd in enumerate(booking) if predicate(cmd))

    commit = max(i for i, cmd in enumerate(booking) if cmd == ("COMMIT",))
    release = at(lambda cmd: cmd[0] == "EVAL" and key in cmd)
    cache_del = at(lambda cmd: cmd[:2] == ("DEL", "cache:seatmap:7"))
    assert commit < release < cache_del
    assert not [cmd for cmd in booking if cmd[:2] == ("DEL", key)]


async def test_a_seatmap_del_that_raises_is_not_retried_and_the_booking_stands(migrated_db, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    from tests.pay.kit import C1, api, clock_at, confirm, count, hold, r_call, user

    db = _pay_world(migrated_db)["db"]
    u = user(db)
    async with api(db, clock_at(), SEATMAP_CACHE_TTL_SECONDS="10") as c:
        h = await hold(c, u, [C1])
        assert (await c.get("/api/showtimes/7/seatmap")).status_code == 200
        redis = c.application.state.redis
        real, attempts = redis.delete, []

        async def failing(*keys):
            if "cache:seatmap:7" in keys:
                attempts.append(keys)
                raise RedisConnectionError("DEL refused")
            return await real(*keys)

        monkeypatch.setattr(redis, "delete", failing)
        r = await confirm(c, u, h["hold_token"])
        left = r_call("PTTL", "cache:seatmap:7")
    assert r.status_code == 201 and count(db, "SELECT count(*) FROM booking") == 1  # not rolled back
    assert len(attempts) == 1  # not retried
    assert 0 < left <= 10000  # the stale entry is gone within SEATMAP_CACHE_TTL_SECONDS on Redis's own clock

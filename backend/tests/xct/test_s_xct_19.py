"""S-XCT-19 (P-XCT-08, SRC-002 §8.2): the seat map and the listings are cache-aside; invalidation is a DEL.

Not here, and why the row stays Blocked: 'after a hold, a release or a booking commits, EXISTS cache:seatmap:41
returns 0' and the recorded command order for one hold (SET lock NX -> COMMIT -> DEL lock -> DEL cache) - the
hold, release and booking paths are Phase 4. app.core.cache.invalidate_seatmap, which those paths will call,
is asserted in tests/brw/test_s_brw_16.py.
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

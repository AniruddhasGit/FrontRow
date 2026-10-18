"""S-BRW-16 (P-BRW-12): cache-aside on the read path, listings invalidated by a generation counter, browsing
alive with Redis gone, and the seat-map stampede guard.

Not here, and why the row stays Blocked:
- 'after an admin PUBLISH commits, the counter has increased by exactly 1' - there is no publish endpoint until
  Phase 6 (admin movie management), and the existing admin writes (app/domain/admin/, another lane's files) do
  not yet call app.core.cache.bump_listing_generation. The function's own command is asserted below.
- 'a booking commit issues DEL cache:seatmap:{id}' and 'the transaction still commits' - booking is Phase 4.
  invalidate_seatmap's behaviour (one DEL, never retried, a WARNING with the request id, expiry) is asserted.
- the rendered page text sweep (browser harness).
"""

from __future__ import annotations

import asyncio
import re
import time

import pytest

from app.core import cache
from app.core.logging import bind_request_id
from app.domain.browse import seatmap as seatmap_module
from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_hall, make_movie, make_screen,
                           make_seat, make_showtime, redis_sync, reset_catalogue)

pytestmark = pytest.mark.anyio

CACHED = {"LISTING_CACHE_TTL_SECONDS": "60", "SEATMAP_CACHE_TTL_SECONDS": "10"}


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_hall(db, make_cinema(db), rows=2, cols=4, categories=[make_category(db)] * 2)
    film = make_movie(db)
    st = make_showtime(db, film, hall["screen_id"], "2026-08-16T19:30:00+05:30")
    return {"db": db, "film": film, "st": st, "hall": hall}


def _clock() -> SetClock:
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    return clock


def record(client) -> list[tuple]:
    """Wrap the application's Redis client: every command it issues, with its result."""
    redis = client.application.state.redis
    log: list[tuple] = []
    original = redis.execute_command

    async def recording(*args, **kwargs):
        try:
            result = await original(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.append((" ".join(str(a) for a in args), exc))
            raise
        log.append((" ".join(str(a) for a in args), result))
        return result

    redis.execute_command = recording
    return log


async def test_listing_and_seatmap_entries_carry_their_ttls(world):
    async with api(world["db"], _clock(), **CACHED) as c:
        log = record(c)
        assert (await c.get("/api/movies")).status_code == 200
        assert (await c.get(f"/api/showtimes/{world['st']}/seatmap")).status_code == 200
    r = redis_sync()
    try:
        listing_keys = [k.decode() for k in r.scan_iter(match="cache:listing:*") if k != b"cache:listing:generation"]
        assert len(listing_keys) == 1 and re.fullmatch(r"cache:listing:\d+:[0-9a-f]+", listing_keys[0])
        assert r.ttl(listing_keys[0]) == 60
        assert r.ttl(f"cache:seatmap:{world['st']}") == 10
    finally:
        r.close()
    commands = [cmd for cmd, _ in log]
    assert any(cmd.startswith("SETEX cache:listing:") for cmd in commands)
    assert not [cmd for cmd in commands if re.match(r"^SET cache:listing:|^SCAN|^(SET|DEL) cache:listing:generation", cmd)]


async def test_a_bump_is_one_incr_and_makes_the_next_read_a_miss(world):
    db = world["db"]
    async with api(db, _clock(), **CACHED) as c:
        await c.get("/api/movies")
        newer = make_movie(db, published_at="2026-08-14T08:00:00+05:30")
        stale = [m["id"] for m in (await c.get("/api/movies")).json()["movies"]]
        log = record(c)
        before = int(redis_sync().get(cache.LISTING_GENERATION) or 0)
        await cache.bump_listing_generation(c.application.state.redis)
        after = int(redis_sync().get(cache.LISTING_GENERATION))
        fresh = [m["id"] for m in (await c.get("/api/movies")).json()["movies"]]
    assert newer not in stale and newer in fresh
    assert after == before + 1
    assert [cmd for cmd, _ in log if cmd.startswith("INCR")] == ["INCR cache:listing:generation"]


async def test_a_deleted_counter_incrs_to_one_and_reads_still_work(world):
    async with api(world["db"], _clock(), **CACHED) as c:
        await c.get("/api/movies")
        r = redis_sync()
        r.delete(cache.LISTING_GENERATION)
        await cache.bump_listing_generation(c.application.state.redis)
        assert int(r.get(cache.LISTING_GENERATION)) == 1
        r.close()
        assert (await c.get("/api/movies")).status_code == 200


async def test_a_failed_seatmap_del_is_not_retried_logs_a_warning_and_the_entry_expires(world, log_capture):
    async with api(world["db"], _clock(), SEATMAP_CACHE_TTL_SECONDS="1") as c:
        await c.get(f"/api/showtimes/{world['st']}/seatmap")
        redis = c.application.state.redis
        calls: list[str] = []

        async def broken_delete(*keys):
            calls.append(" ".join(keys))
            raise ConnectionError("a Redis blip")

        redis.delete = broken_delete
        with bind_request_id("abcd1234"):
            await cache.invalidate_seatmap(redis, world["st"])  # must not raise
    assert calls == [f"cache:seatmap:{world['st']}"]
    warnings = [ln for ln in log_capture.lines() if ln["level"] == "WARNING" and ln["request_id"] == "abcd1234"]
    assert len(warnings) == 1
    await asyncio.sleep(1.5)
    r = redis_sync()
    try:
        assert r.ttl(f"cache:seatmap:{world['st']}") == -2
    finally:
        r.close()


async def test_a_working_seatmap_invalidation_is_a_del(world):
    async with api(world["db"], _clock(), **CACHED) as c:
        await c.get(f"/api/showtimes/{world['st']}/seatmap")
        log = record(c)
        await cache.invalidate_seatmap(c.application.state.redis, world["st"])
    assert [cmd for cmd, _ in log] == [f"DEL cache:seatmap:{world['st']}"]
    assert redis_sync().exists(f"cache:seatmap:{world['st']}") == 0


async def test_five_concurrent_misses_one_rebuild_lock_and_four_losers_reading_postgres(world, monkeypatch):
    original = seatmap_module.load_seatmap
    calls = {"n": 0}

    async def slow_first(conn, showtime_id):
        calls["n"] += 1
        first = calls["n"] == 1
        result = await original(conn, showtime_id)
        if first:
            await asyncio.sleep(0.6)  # the winner is still building when the losers re-read
        return result

    monkeypatch.setattr(seatmap_module, "load_seatmap", slow_first)
    async with api(world["db"], _clock(), **CACHED) as c:
        log = record(c)
        c.statements.reset()
        url = f"/api/showtimes/{world['st']}/seatmap"

        async def timed():
            started = time.perf_counter()
            response = await c.get(url)
            return response, time.perf_counter() - started

        results = await asyncio.gather(*(timed() for _ in range(5)))
    assert [r.status_code for r, _ in results] == [200] * 5
    assert all(elapsed < 2.0 for _, elapsed in results)
    rebuilds = [(cmd, res) for cmd, res in log if cmd.startswith(f"SET cache:seatmap:{world['st']}:rebuild")]
    assert len(rebuilds) == 5 and all("NX" in cmd and "PX 2000" in cmd for cmd, _ in rebuilds)
    assert sum(1 for _, res in rebuilds if res) == 1
    seat_queries = c.statements.matching("showtime_seat")
    assert seat_queries == 5  # the winner's one, and each of the four losers' own
    gets = [cmd for cmd, _ in log if cmd == f"GET cache:seatmap:{world['st']}"]
    assert len(gets) == 5 + 4  # every caller's first read, and one re-read per loser


async def test_with_redis_stopped_the_listings_are_byte_identical_and_still_200(world):
    db = world["db"]
    params = {"movie_id": world["film"], "date": "2026-08-16"}
    async with api(db, _clock(), **CACHED) as up:
        movies_up, showtimes_up = await up.get("/api/movies"), await up.get("/api/showtimes", params=params)
    async with api(db, _clock(), REDIS_URL="redis://redis:1/13", **CACHED) as down:
        movies_down, showtimes_down = await down.get("/api/movies"), await down.get("/api/showtimes", params=params)
    assert (movies_down.status_code, showtimes_down.status_code) == (200, 200)
    assert movies_down.content == movies_up.content and showtimes_down.content == showtimes_up.content


async def test_with_redis_stopped_the_seatmap_fails_closed_with_its_own_sentence(world):
    async with api(world["db"], _clock(), REDIS_URL="redis://redis:1/13") as c:
        r = await c.get(f"/api/showtimes/{world['st']}/seatmap")
    assert r.status_code == 503 and r.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert r.json()["error"]["message"] == ("The seat map is unavailable right now. You can still browse showtimes. "
                                            "Try again in a few minutes.")


def test_the_stampede_site_names_the_scenario():
    from tests.xct._support import rg

    assert rg("stampede", "backend/app/core/cache.py", fixed=True)

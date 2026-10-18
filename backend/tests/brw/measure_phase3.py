"""The Phase 3 seat-map measurement (P-BRW-13, P-BRW-14, FR-ADR-045): measured, never invented.

    docker compose --profile test run --rm test python -m tests.brw.measure_phase3

Prints docs/10 EngineeringLedger/PHASE3_MEASUREMENTS.tsv's content on stdout. Not a test (no test_ prefix): it
seeds a throwaway database with scripts/seed.py, runs the real application in-process, and measures it.

WHAT IT IS NOT: a measurement of AWS. It runs in the test container on local Docker Desktop, over httpx's ASGI
transport (no socket, no network, no load balancer), against the compose PostgreSQL 16 and Redis 7. Every figure
is therefore a lower bound on what a t3.micro behind an ALB will show, and is labelled so in the Method column.
"""

from __future__ import annotations

import asyncio
import statistics
import time

import httpx

from app.core import cache
from app.main import create_app
from tests.brw.kit import SetClock, flush_redis, settings_for
from tests.dbkit import create_database, drop_database, owner_sql
from tests.seed.kit import NOW, run_seed
from tests.test_health import ok_probe

VIEWERS = 10
POLL_SECONDS = 3
DURATION_SECONDS = 30
TIMED_REQUESTS = 200


async def main() -> None:
    db = create_database(migrate=True)
    try:
        code, lines = run_seed(db.app_url)
        assert code == 0, lines
        showtime_id, seats = owner_sql(db, "SELECT ss.showtime_id, count(*) FROM showtime_seat ss GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1")[0]
        assert seats == 220, seats
        flush_redis()
        settings = settings_for(db, LISTING_CACHE_TTL_SECONDS="60", SEATMAP_CACHE_TTL_SECONDS="10")
        clock = SetClock()
        clock.set(NOW)
        app = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
        url = f"/api/showtimes/{showtime_id}/seatmap"
        async with app.router.lifespan_context(app):
            redis = app.state.redis
            gets = {"hit": 0, "miss": 0}
            original_get = redis.get

            async def counting_get(key, *a, **kw):
                value = await original_get(key, *a, **kw)
                if key == cache.seatmap_key(showtime_id):
                    gets["hit" if value is not None else "miss"] += 1
                return value

            def client(i: int) -> httpx.AsyncClient:
                transport = httpx.ASGITransport(app=app, client=(f"10.1.0.{i + 1}", 40000))
                return httpx.AsyncClient(transport=transport, base_url="http://testserver")

            # 1. size: the 220-seat map, and the default listing beside it (P-BRW-13's reversal observable)
            async with client(200) as c:
                seatmap_bytes = len((await c.get(url)).content)
                listing_bytes = len((await c.get("/api/movies")).content)

            # 2. response time: TIMED_REQUESTS sequential reads, cache warm and cold mixed as polling produces them
            durations = []
            for i in range(TIMED_REQUESTS):
                async with client(i % 100) as c:
                    started = time.perf_counter()
                    r = await c.get(url)
                    durations.append((time.perf_counter() - started) * 1000)
                    assert r.status_code == 200
            cold = []
            for _ in range(20):
                await redis.delete(cache.seatmap_key(showtime_id))
                async with client(150) as c:
                    started = time.perf_counter()
                    await c.get(url)
                    cold.append((time.perf_counter() - started) * 1000)

            # 3. hit rate: VIEWERS pollers, one address each, every POLL_SECONDS for DURATION_SECONDS of real time
            redis.get = counting_get
            await redis.delete(cache.seatmap_key(showtime_id))

            async def viewer(i: int) -> None:
                async with client(i) as c:
                    end = time.perf_counter() + DURATION_SECONDS
                    await asyncio.sleep(i * POLL_SECONDS / VIEWERS)
                    while time.perf_counter() < end:
                        assert (await c.get(url)).status_code == 200
                        await asyncio.sleep(POLL_SECONDS)

            await asyncio.gather(*(viewer(i) for i in range(VIEWERS)))
            redis.get = original_get
        reads = gets["hit"] + gets["miss"]
        method = ("in-process ASGI (httpx ASGITransport, no network) in the test container on local Docker Desktop against "
                  "compose PostgreSQL 16 + Redis 7, scripts/seed.py catalogue, NOT a t3.micro and NOT behind an ALB")
        rows = [
            ("seatmap_response_bytes", str(seatmap_bytes), str(seatmap_bytes), "1",
             f"len(body) of GET {url.replace(str(showtime_id), '{id}')} for the seeded 220-seat hall, uncompressed; {method}"),
            ("seatmap_response_ms", f"{max(durations):.1f}", f"{statistics.median(durations):.1f}", str(len(durations)),
             f"{len(durations)} sequential reads as polling produces them (mostly cache hits); {method}"),
            ("seatmap_response_ms_cache_miss", f"{max(cold):.1f}", f"{statistics.median(cold):.1f}", str(len(cold)),
             f"{len(cold)} reads each after DEL of the cache entry (PostgreSQL + the 220 lock keys); {method}"),
            ("seatmap_cache_hit_rate", f"{gets['hit']}/{reads}", f"{gets['hit']}/{reads}", str(reads),
             f"{VIEWERS} viewers polling every {POLL_SECONDS}s for {DURATION_SECONDS}s of real time, TTL 10s; hits/reads of "
             f"cache:seatmap:{{id}}; {method}"),
            ("listing_response_bytes", str(listing_bytes), str(listing_bytes), "1",
             f"len(body) of GET /api/movies with no filters over the seeded catalogue; compare with seatmap_response_bytes "
             f"(P-BRW-13: pagination is worth adding only when this exceeds that); {method}"),
        ]
        print("Metric\tWorst\tMedian\tSamples\tMethod")
        for row in rows:
            print("\t".join(row))
    finally:
        drop_database(db)


if __name__ == "__main__":
    asyncio.run(main())

"""Cache-aside for the public read path (P-BRW-12, P-XCT-08, FR-ADR-030), and the Redis key names it uses.

    cache:seatmap:{showtime_id}                    the seat map, SEATMAP_CACHE_TTL_SECONDS (10 s)
    cache:seatmap:{showtime_id}:rebuild            the stampede guard, CACHE_REBUILD_LOCK_TTL_MS
    cache:listing:generation                       one integer; INCR after an admin write that changes a listing
    cache:listing:{generation}:{fingerprint}       a movie or showtime listing, LISTING_CACHE_TTL_SECONDS (60 s)
    lock:seat:{showtime_id}:{seat_id}              a seat hold's lock (written by the Phase 4 hold path; read here)

RULES. Invalidation is a DEL issued after commit and never a SET: a writer that computes the new value can lose
to a slower reader holding an older one, while a DEL writes nothing and so cannot write a stale value. A failed
DEL is not retried and nothing is rolled back; the entry expires within its TTL, which is the stated bound.
The listings cannot be DEL'd - their keyspace is one key per filter combination, which no writer can name - so a
write INCRs the generation instead and every older key becomes unreachable and expires on its own. A missing
counter is not an error: the next INCR makes it 1. Resetting it is forbidden (an old generation's keys would be
reachable again).

REDIS DOWN. The listings treat an outage exactly as a miss and serve from PostgreSQL (FR-ADR-028). The seat map
does not: its rate limiter fails closed first (FR-ADR-058, P-BRW-12 X-7), and its held state lives only in Redis,
so every Redis error on that path propagates to the caller, which answers 503.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable

from redis.exceptions import RedisError

from app.core.config import Settings

log = logging.getLogger("app.cache")

LISTING_GENERATION = "cache:listing:generation"

# Compare-and-delete: only the caller holding the rebuild token releases it. A plain DEL after a slow rebuild
# could delete the NEXT rebuilder's lock once ours has expired, and two callers would rebuild at once.
_RELEASE = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"

# [JUDGMENT CALL] How long a caller that lost the rebuild lock waits before its one re-read: a tenth of the lock's
# lifetime (200 ms at the default). No source states it. Long enough for an ordinary rebuild (tens of ms) to land,
# so the loser is served from the cache; short enough that a loser behind a slow rebuild still answers well inside
# the lock's lifetime by reading PostgreSQL itself.
_REBUILD_WAIT_FRACTION = 10


def seatmap_key(showtime_id: int) -> str:
    return f"cache:seatmap:{showtime_id}"


def seat_lock_key(showtime_id: int, seat_id: int) -> str:
    """The per-seat hold lock (03_concurrency_model.md). One key per seat, never one per group (P-HLD-08)."""
    return f"lock:seat:{showtime_id}:{seat_id}"


async def listing(redis, settings: Settings, fingerprint: str, build: Callable[[], Awaitable[bytes]]) -> bytes:
    """A movie or showtime listing, cache-aside under the current generation. Redis failing is a miss."""
    ttl = settings.LISTING_CACHE_TTL_SECONDS
    if ttl == 0:
        return await build()
    try:
        generation = (await redis.get(LISTING_GENERATION) or b"0").decode()
        key = f"cache:listing:{generation}:{fingerprint}"
        hit = await redis.get(key)
    except (RedisError, OSError):
        # A cache outage and a cache miss are the same event to a cache-aside reader (P-BRW-12 rows 1 and 6).
        return await build()
    if hit is not None:
        return hit
    body = await build()
    try:
        await redis.setex(key, ttl, body)
    except (RedisError, OSError):
        pass  # the response is already correct; the next read is a miss again
    return body


async def bump_listing_generation(redis) -> None:
    """Called AFTER an admin write that can change any listing has committed. Never rolls the write back."""
    try:
        # INCR itself, not redis-py's incr() (which sends INCRBY key 1): the command the runbook and the tests name.
        await redis.execute_command("INCR", LISTING_GENERATION)
    except (RedisError, OSError):
        # P-BRW-12 rows 5 and 7: listings are stale for at most LISTING_CACHE_TTL_SECONDS; the write stands.
        log.warning("listing generation INCR failed; listings may be stale until their TTL", exc_info=True)


async def invalidate_seatmap(redis, showtime_id: int) -> None:
    """Called AFTER a hold, a release or a booking has committed. One DEL, never retried, never a SET."""
    try:
        await redis.delete(seatmap_key(showtime_id))
    except (RedisError, OSError):
        # P-XCT-08 exception 1: the entry expires within SEATMAP_CACHE_TTL_SECONDS. Retrying would only move the
        # failure; rolling back would undo a customer's booking to fix a cache.
        log.warning("seat map cache DEL failed; the entry expires within its TTL", exc_info=True,
                    extra={"showtime_id": showtime_id})


async def seatmap(redis, settings: Settings, showtime_id: int, build: Callable[[], Awaitable[bytes]]) -> bytes:
    """The seat map, cache-aside, with a per-key rebuild lock. Redis errors propagate (the caller answers 503)."""
    key = seatmap_key(showtime_id)
    hit = await redis.get(key)
    if hit is not None:
        return hit
    ttl = settings.SEATMAP_CACHE_TTL_SECONDS
    if ttl == 0:
        return await build()
    # STAMPEDE GUARD (SRC-002 §8.2.3). The scenario: the 10-second entry for a popular Friday-evening showtime
    # expires while forty viewers are polling it every three seconds, and every one of them misses at once and
    # rebuilds it from PostgreSQL - forty copies of the largest query in the product, on a t3.micro, at the busiest
    # moment. What prevents it: one caller wins `SET cache:seatmap:{id}:rebuild NX PX CACHE_REBUILD_LOCK_TTL_MS` and
    # rebuilds; a loser waits a short while, re-reads ONCE, and on a second miss reads PostgreSQL itself rather than
    # queueing behind the lock - nobody blocks on a lock they cannot get (P-BRW-12 row 4).
    lock_key, token = f"{key}:rebuild", secrets.token_hex(8)
    if await redis.set(lock_key, token, nx=True, px=settings.CACHE_REBUILD_LOCK_TTL_MS):
        try:
            body = await build()
            await redis.setex(key, ttl, body)
        finally:
            await redis.eval(_RELEASE, 1, lock_key, token)
        return body
    await asyncio.sleep(settings.CACHE_REBUILD_LOCK_TTL_MS / _REBUILD_WAIT_FRACTION / 1000)
    hit = await redis.get(key)
    if hit is not None:
        return hit
    return await build()

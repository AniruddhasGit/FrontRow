"""The seat lock primitives (FR-ADR-025, P-HLD-01, 03_concurrency_model.md). Two operations and nothing else.

ACQUIRE is ONE command: `SET lock:seat:{s}:{seat} <token> NX PX <ttl_ms>`. Never SETNX then EXPIRE - a process
that dies between the two leaves a seat locked forever with no error anywhere (GOTCHAS).

RELEASE is the compare-and-delete Lua script, verbatim from FR-ADR-025. Never GET then DEL from Python: A's lock
expires, B acquires the seat, A's late release would delete B's lock while B pays.

Expiry is Redis's. Nothing here reads a clock, and no cleanup job exists or is needed (FR-ADR-026).
"""

from __future__ import annotations

RELEASE = 'if redis.call("GET", KEYS[1]) == ARGV[1] then return redis.call("DEL", KEYS[1]) else return 0 end'


def seat_key(showtime_id: int, seat_id: int) -> str:
    return f"lock:seat:{showtime_id}:{seat_id}"


async def acquire(redis, key: str, token: str, ttl_ms: int) -> bool:
    """True when this call took the key. The argument order is the documented form, sent as one command."""
    return bool(await redis.execute_command("SET", key, token, "NX", "PX", ttl_ms))


async def release(redis, key: str, token: str) -> bool:
    """True when the key held `token` and was deleted; False when it was gone or someone else's (not an error)."""
    return bool(await redis.eval(RELEASE, 1, key, token))

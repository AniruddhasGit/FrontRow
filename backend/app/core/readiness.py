"""Readiness probes and their cache  -  ZONE B (SRC-002 §6.2.3, PRD P-XCT-10 / S7.7).

/health/ready asks: can this instance serve real traffic? It checks PostgreSQL with `SELECT 1` and
Redis with `PING`, each on its own short timeout, and nothing else. SQS, SES and S3 are deliberately
not probed: the API serves almost every request without them, and probing them would take the site
out of service for a failure it can absorb.

The result is cached for READINESS_CACHE_TTL_SECONDS so continuous load balancer polling does not run
one database connection per poll per instance.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.clock import Clock

log = logging.getLogger("app.readiness")


@dataclass(frozen=True)
class Probe:
    name: str
    check: Callable[[], Awaitable[None]]
    # The hard ceiling for this probe. Without it a dependency that accepts the TCP connection and
    # then never answers (a half-dead node, a full listen backlog) hangs the readiness request until
    # the LOAD BALANCER times out - slower, and it tells the operator nothing about which one hung.
    timeout_s: float


@dataclass(frozen=True)
class ReadinessResult:
    checks: dict[str, str]  # name -> "ok" | "unreachable"

    @property
    def ok(self) -> bool:
        return all(v == "ok" for v in self.checks.values())


class Readiness:
    def __init__(self, probes: list[Probe], ttl_s: float, clock: Clock) -> None:
        # The dependencies checked: PostgreSQL and Redis only (module docstring).
        self._probes = probes
        # READINESS_CACHE_TTL_SECONDS. Without a cache every load balancer poll opens a database connection.
        self._ttl_s = ttl_s
        # Injected, so a test moves the cache's age without sleeping.
        self._clock = clock
        # Nothing cached yet, and -inf as its age: the FIRST poll always probes, never answers from nothing.
        self._cached: ReadinessResult | None = None
        self._cached_at = -math.inf
        # Without this lock, N polls arriving while the cache is stale each open their own database
        # connection at the same moment - a small stampede on exactly the dependency that is slow.
        self._lock = asyncio.Lock()

    def _fresh(self) -> bool:
        # Younger than the TTL: answer from the cache. Without this comparison every poll probes.
        return self._cached is not None and (self._clock.monotonic() - self._cached_at) < self._ttl_s

    async def check(self) -> ReadinessResult:
        if self._fresh():
            return self._cached  # type: ignore[return-value]
        async with self._lock:
            if self._fresh():  # someone else probed while we waited for the lock
                return self._cached  # type: ignore[return-value]
            # Probes run concurrently, so the worst case is the slowest timeout, not the sum.
            outcomes = await asyncio.gather(*(self._run(p) for p in self._probes))
            result = ReadinessResult(checks=dict(outcomes))
            if not result.ok:
                # One line naming the whole state, so "why was this instance pulled from the load
                # balancer" is one search, not a reconstruction from per-probe lines.
                log.warning("not ready", extra={"checks": result.checks})
            # A FAILED result is cached too. Without that, during an outage every poll waits out a
            # full probe timeout, and the readiness endpoint itself becomes the slow request.
            self._cached, self._cached_at = result, self._clock.monotonic()
            return result

    async def _run(self, probe: Probe) -> tuple[str, str]:
        try:
            # The timeout is ENFORCED here, per probe. Without wait_for a dependency that accepts the
            # connection and never answers hangs /health/ready until the load balancer gives up.
            await asyncio.wait_for(probe.check(), timeout=probe.timeout_s)
            return probe.name, "ok"
        except Exception as exc:  # noqa: BLE001 - any failure at all means "not ready"
            # The exception TYPE only, never str(exc) in the response; the log gets both, scrubbed of
            # URL credentials by the formatter.
            log.warning(
                "readiness probe failed",
                extra={"probe": probe.name, "error_type": type(exc).__name__, "error": str(exc)[:300]},
            )
            return probe.name, "unreachable"


def postgres_probe(database_url: str, timeout_ms: int) -> Probe:
    """`SELECT 1` on a fresh connection. Phase 1 has no pool; Phase 2 replaces this with a pool check.

    A fresh connection per probe is acceptable only because the cache bounds it to one connection
    per READINESS_CACHE_TTL_SECONDS per instance.

    KNOWN, NOT FIXED: psycopg resolves the host with loop.getaddrinfo, which runs in the default
    thread pool. The 1 s ceiling cancels the await but cannot stop that thread, and asyncio.run joins
    the pool at exit. Locally, a stopped compose container's name takes ~4 s to fail resolution, so
    SIGTERM with Postgres down exits up to ~4 s late (still 0, still inside the 30 s grace period).
    connect_timeout does not help: it starts after resolution. An RDS endpoint name keeps resolving
    while the database is down, so this is reasoned to be local-only.
    """
    import psycopg  # imported here so the unit tests that inject fake probes never need a driver

    async def check() -> None:
        # libpq's connect_timeout is whole seconds with an effective minimum of 2; the asyncio
        # ceiling in Readiness._run is the real bound. Both exist so neither is the only guard.
        # autocommit: SELECT 1 must not leave a transaction open on the server if the close below is
        # interrupted by the timeout; an idle-in-transaction connection holds a slot until it is killed.
        conn = await psycopg.AsyncConnection.connect(
            database_url, connect_timeout=max(2, math.ceil(timeout_ms / 1000)), autocommit=True
        )
        try:
            # The cheapest statement that proves the server answers queries, not merely accepts connections.
            await conn.execute("SELECT 1")
        finally:
            # Without it one connection leaks per probe, and the database runs out of slots on a quiet day.
            await conn.close()

    return Probe(name="postgres", check=check, timeout_s=timeout_ms / 1000)


def redis_probe(client: "object", timeout_ms: int) -> Probe:
    """PING on the process's shared Redis client. timeout_ms is connect + command (app/main.py passes the
    sum): a probe on a fresh connection pays both, so a smaller ceiling would call a cold, healthy Redis
    unreachable. The client itself has retries off, so a dead node fails once, not (retries + 1) times."""

    async def check() -> None:
        # The same client the rate limiter uses: if this PING fails, so would every limited request.
        await client.ping()  # type: ignore[attr-defined]

    return Probe(name="redis", check=check, timeout_s=timeout_ms / 1000)

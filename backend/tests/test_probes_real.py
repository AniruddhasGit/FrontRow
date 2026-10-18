"""The REAL probe functions (psycopg, redis-py) against a port nothing listens on.

Fake probes prove the handler; these prove the real drivers fail fast and are reported as
"unreachable" rather than raising out of the endpoint or hanging. The stopped-container proof in the
GOAL_14 gate is the third layer.
"""

from __future__ import annotations

import asyncio

from app.core.clock import SystemClock
from app.core.readiness import Readiness, postgres_probe, redis_probe
from app.main import _real_redis_client
from app.core.config import Settings

CLOSED = "127.0.0.1:1"  # port 1: nothing listens there inside the test container


def test_real_postgres_probe_reports_unreachable(log_capture):
    readiness = Readiness([postgres_probe(f"postgresql://u:pw@{CLOSED}/x", 1000)], ttl_s=0, clock=SystemClock())
    result = asyncio.run(readiness.check())
    assert result.checks == {"postgres": "unreachable"}


def test_real_redis_probe_reports_unreachable(clean_env, log_capture):
    settings = Settings(DATABASE_URL="postgresql://u:pw@db/x", REDIS_URL=f"redis://{CLOSED}/0")

    async def scenario():
        client = _real_redis_client(settings)
        try:
            r = Readiness([redis_probe(client, 1000)], ttl_s=0, clock=SystemClock())
            return await r.check()
        finally:
            await client.aclose()

    assert asyncio.run(scenario()).checks == {"redis": "unreachable"}

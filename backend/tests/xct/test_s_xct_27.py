"""S-XCT-27 (P-XCT-13, EP-XCT-03): /metrics in Prometheus text format, and the written statement that nothing scrapes it.

The api is the real app on the booking lane's kit (Redis command log, injected clock). The worker's listener is
app.core.metrics.serve on an ephemeral port. Counters are process-global, so each test reads a delta or resets them.

NOT asserted here (the row stays Blocked on them):
- "a queue_depth_age_seconds series beside it" against "a list of exactly eight and failing on a ninth": the two
  clauses contradict for the failure scrape. Here the eighth-only list holds on every healthy scrape and the age series
  appears ONLY while queue_depth is stale - both halves are asserted, each on its own scrape.
- seat_locks_held "from an O(1) counter ... reconciled by a bounded SCAN on the worker's existing receive loop": the
  gauge is SCARD of this instance's hold registry (O(1), one command, no SCAN), not an INCR/DECR counter, and no
  worker reconcile exists - that needs the hold lane's acquire/release paths (ponytail note in app/api/metrics.py).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.core import metrics
from tests.conftest import VALID_ENV
from tests.pay.kit import C1, api, book, clock_at, confirm, hold, user, world7
from tests.xct._support import rg

pytestmark = pytest.mark.anyio

EIGHT = {"http_requests_total", "http_request_duration_seconds", "seat_locks_held", "queue_depth", "seat_conflicts_total",
         "booking_confirmations_total", "receipt_dispatch_total", "outbox_pending"}
BACKEND_DIR = Path(__file__).resolve().parents[2]


def families(body: str) -> set[str]:
    return {ln.split()[2] for ln in body.splitlines() if ln.startswith("# TYPE ")}


def value(body: str, series: str) -> float:
    found = [ln.rsplit(" ", 1)[1] for ln in body.splitlines() if ln.split(" ")[0] == series]
    return float(found[0]) if found else 0.0


class Depth:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    async def __call__(self) -> int:
        self.calls += 1
        if self.fail:
            raise ConnectionError("SQS unroutable (stub)")
        return 7


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_the_scrape_is_prometheus_text_with_exactly_the_eight_series_and_one_redis_command(world):
    async with api(world["db"], clock_at()) as c:
        await c.get("/health/live")  # one request so the request series carry a sample
        c.redis_log.reset()
        r = await c.get("/metrics")
        sent = list(c.redis_log.commands)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; version=0.0.4"
    assert families(r.text) == EIGHT and len(families(r.text)) == 8
    assert [cmd[0].upper() for cmd in sent] == ["SCARD"]
    assert rg(r"scan_iter|SCAN", "backend/app/api/metrics.py") == []


async def test_a_seat_conflict_at_confirm_increments_seat_conflicts_total(world):
    db = world["db"]
    u, other = user(db), user(db)
    async with api(db, clock_at()) as c:
        before = value((await c.get("/metrics")).text, "seat_conflicts_total")
        lone = await hold(c, u, [C1])
        book(db, other, 7, [C1])  # the lock was won, the constraint decides (S-XCT-03's own setup)
        lost = await confirm(c, u, lone["hold_token"], key="k-metrics")
        after = (await c.get("/metrics")).text
    assert lost.status_code == 409
    assert value(after, "seat_conflicts_total") == before + 1
    assert 'booking_confirmations_total{outcome="seat_unavailable"}' in after


async def test_two_scrapes_one_second_apart_make_one_queue_call_and_a_dead_queue_keeps_the_last_value(world):
    clock = clock_at()
    stub = Depth()
    async with api(world["db"], clock) as c:
        c.application.state.queue_depth = metrics.QueueDepth(stub, clock.monotonic)
        first = (await c.get("/metrics")).text
        clock.advance(1)
        second = (await c.get("/metrics")).text
        assert stub.calls == 1
        stub.fail = True
        clock.advance(metrics.QueueDepth.CACHE_SECONDS)
        stale = await c.get("/metrics")
    assert value(first, "queue_depth") == value(second, "queue_depth") == 7
    assert families(second) == EIGHT  # healthy: eight, no ninth
    assert stale.status_code == 200 and stub.calls == 2
    assert value(stale.text, "queue_depth") == 7
    assert value(stale.text, "queue_depth_age_seconds") == 1 + metrics.QueueDepth.CACHE_SECONDS


async def test_the_worker_listener_serves_the_same_exposition():
    async def gauges():
        return {"outbox_pending": 3}, None

    server = await metrics.serve(0, gauges)
    port = server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"http://127.0.0.1:{port}/metrics")
            missing = await client.get(f"http://127.0.0.1:{port}/other")
    finally:
        server.close()
        await server.wait_closed()
    assert r.status_code == 200 and r.headers["content-type"] == "text/plain; version=0.0.4"
    assert families(r.text) == EIGHT and value(r.text, "outbox_pending") == 3
    assert missing.status_code == 404


@pytest.mark.parametrize("port", ["8000", "80", "70000"])
def test_the_worker_refuses_a_metrics_port_equal_to_the_api_port_or_out_of_range(tmp_path, port):
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({**VALID_ENV, "API_PORT": "8000", "WORKER_METRICS_PORT": port, "PYTHONPATH": str(BACKEND_DIR)})
    proc = subprocess.run([sys.executable, "-m", "app", "worker"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "WORKER_METRICS_PORT" in proc.stderr


def test_one_uvicorn_worker_and_the_deployment_spec_says_nothing_scrapes_it():
    hits = rg(r"workers", "backend/entrypoint.sh")
    assert all(line.strip().endswith("1") for _, _, line in hits)
    assert rg("/metrics", "docs/30 Deployment", fixed=True)
    assert rg("No load balancer listener rule may match /metrics", "docs/30 Deployment", fixed=True)
    assert rg("Nothing scrapes this endpoint, nothing stores its history and nothing alerts on it.", "docs/30 Deployment", fixed=True)

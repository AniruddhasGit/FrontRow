"""S-XCT-21 (PRD P-XCT-10, S7.7, EP-XCT-01/02): /health/live and /health/ready, deliberately different.

Phase 1 has no SQLAlchemy engine, so the AC's "counting SQLAlchemy listener" and "counting Redis
client wrapper" are the counting probes below: the readiness probes are the only code in the process
that issues SELECT 1 or PING. The stopped-container proof (T-P1-03/04) is run against real
containers and recorded in the lane report, not here.
"""

from __future__ import annotations

import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.readiness import Probe
from app.main import create_app

from ..conftest import VALID_ENV
from ..test_health import failing_probe, ok_probe
from ._support import prep_queue, rg
from .test_s_xct_29 import _boot_env, _free_port, _refused

BACKEND_DIR = Path(__file__).resolve().parents[2]

LEAK = re.compile(r"(version|hostname|postgres://|redis://)")


class Counter:
    def __init__(self) -> None:
        self.n = 0


def counting(name: str, counter: Counter, fail: bool = False) -> Probe:
    async def check() -> None:
        counter.n += 1
        if fail:
            raise ConnectionRefusedError(name)

    return Probe(name=name, check=check, timeout_s=0.5)


def _client(clock, probes, **settings_overrides) -> TestClient:
    return TestClient(create_app(Settings(**{**VALID_ENV, **settings_overrides}), clock=clock, probes=probes))


def test_live_is_200_fixed_body_and_issues_no_query_and_no_command(valid_env, clock, log_capture):
    pg, rd = Counter(), Counter()
    with _client(clock, [counting("postgres", pg, fail=True), counting("redis", rd, fail=True)]) as c:
        r = c.get("/health/live")
    assert (r.status_code, r.json()) == (200, {"status": "live"})
    assert (pg.n, rd.n) == (0, 0)


def test_live_issues_no_statement_on_the_request_path_engine(valid_env, clock, log_capture):
    """The counting SQLAlchemy listener the criterion names, on the engine the application serves
    requests with (app/db, Phase 2). /health/live must not reach it."""
    from sqlalchemy import event

    from app.db import make_engine

    settings = Settings(**VALID_ENV)
    engine = make_engine(settings)
    statements = Counter()

    def count(*_args, **_kwargs) -> None:
        statements.n += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    app = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")], engine=engine)
    with TestClient(app) as c:
        for _ in range(2):
            assert c.get("/health/live").status_code == 200
    assert statements.n == 0


def test_ready_200_body_carries_checks_and_payment_provider(valid_env, clock, log_capture):
    pg, rd = Counter(), Counter()
    with _client(clock, [counting("postgres", pg), counting("redis", rd)]) as c:
        r = c.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}, "payment_provider": "simulated"}
    assert (pg.n, rd.n) == (1, 1)


@pytest.mark.parametrize("down", [("postgres",), ("redis",), ("postgres", "redis")])
def test_ready_503_names_what_is_down_while_live_stays_200(valid_env, clock, log_capture, down):
    probes = [counting(n, Counter(), fail=n in down) for n in ("postgres", "redis")]
    with _client(clock, probes) as c:
        r = c.get("/health/ready")
        live = c.get("/health/live")
    assert r.status_code == 503
    for name in down:
        assert r.json()["checks"][name] != "ok"
    assert r.json()["payment_provider"] == "simulated"
    assert live.status_code == 200


@pytest.mark.parametrize(
    "override",
    [
        {"QUEUE_URL": "http://10.255.255.1:9324/000000000000/frontrow-receipts"},
        {"AWS_REGION": "xx-nowhere-1", "MAIL_PROVIDER": "ses"},
        {"S3_BUCKET_NAME": "frontrow-unroutable-bucket", "AWS_REGION": "xx-nowhere-1"},
    ],
)
def test_ready_ignores_ses_sqs_and_s3(valid_env, clock, log_capture, override):
    with _client(clock, [ok_probe("postgres"), ok_probe("redis")], **override) as c:
        assert c.get("/health/ready").status_code == 200


def test_ready_503_in_under_2s_against_a_blackholed_postgres():
    """A listener that accepts into its backlog and never answers: the TCP connect succeeds and the
    PostgreSQL handshake hangs - a blackhole, not a refusal. The real server process is asked with a
    10-second client timeout, so a 503 inside 2 seconds is the server's own timeout. Elapsed time is
    measured with the real monotonic clock because the server's REAL timeout is the thing under test."""
    hole = socket.socket()
    hole.bind(("127.0.0.1", 0))
    hole.listen(16)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app", "api"],
        cwd=BACKEND_DIR,
        env=_boot_env(API_PORT=str(port), DATABASE_URL=f"postgresql://u:pw@127.0.0.1:{hole.getsockname()[1]}/x"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(200):  # a startup bound by count (200 x 0.1 s), never by a clock reading (S-SEA-08)
            if not _refused(port) or proc.poll() is not None:
                break
            time.sleep(0.1)
        started = time.monotonic()
        r = httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=10)
        elapsed = time.monotonic() - started
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=20)
        finally:
            if proc.poll() is None:
                proc.kill()
            hole.close()
    assert r.status_code == 503
    assert r.json()["checks"]["postgres"] != "ok"
    assert elapsed < 2.0, elapsed


def test_a_second_request_inside_the_cache_ttl_probes_nothing(valid_env, clock, log_capture):
    pg, rd = Counter(), Counter()
    with _client(clock, [counting("postgres", pg), counting("redis", rd)], READINESS_CACHE_TTL_SECONDS=3) as c:
        c.get("/health/ready")
        clock.advance(2.5)
        c.get("/health/ready")
    assert (pg.n, rd.n) == (1, 1)


def test_neither_endpoint_needs_a_session_nor_leaks_version_host_or_connection_string(valid_env, clock, log_capture):
    with _client(clock, [ok_probe("postgres"), ok_probe("redis")]) as c:
        c.cookies.clear()
        bodies = [c.get(p) for p in ("/health/live", "/health/ready")]
    for r in bodies:
        assert r.status_code == 200
        assert not LEAK.search(r.text), r.text


def test_live_handler_says_what_breaks_if_it_touches_a_dependency():
    assert rg("restart loop", "backend/app/api/health.py", fixed=True)


def test_the_load_balancer_row_names_health_ready():
    rows = [r for r in prep_queue() if "Load Balancer" in r["Item"]]
    assert rows and any("/health/ready" in r["Item"] for r in rows)


def test_the_deployment_spec_says_reversing_them_is_a_restart_loop():
    assert rg("reversing them turns a recoverable outage into a restart loop", "docs/30 Deployment", fixed=True)


@pytest.mark.parametrize(
    "override",
    [
        {"QUEUE_URL": "http://10.255.255.1:9324/000000000000/frontrow-receipts"},
        {"AWS_REGION": "xx-nowhere-1", "MAIL_PROVIDER": "ses"},
        {"S3_BUCKET_NAME": "frontrow-unroutable-bucket", "AWS_REGION": "xx-nowhere-1"},
    ],
)
def test_the_default_probe_list_is_postgres_and_redis_and_nothing_else(valid_env, clock, override):
    """The test above injects its own probes, so it cannot see the DEFAULT list. This one builds the app the way
    boot does (probes=None) and reads the list the lifespan installed: an SQS, SES or S3 probe added there fails
    here. Nothing is probed - the lifespan only builds the list."""
    application = create_app(Settings(**{**VALID_ENV, **override}), clock=clock)
    with TestClient(application):
        names = [p.name for p in application.state.readiness._probes]
    assert names == ["postgres", "redis"]

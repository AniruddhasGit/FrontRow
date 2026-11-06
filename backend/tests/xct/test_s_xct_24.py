"""S-XCT-24 (PRD P-XCT-12, S7.8): JSON logs to stdout with a request id we generate.

The clauses already proved by tests/test_logging.py are cited there, not repeated: the seven keys on
captured lines, the 8-hex id, the forged inbound id, one completion line. This file adds the real
process's own stdout, the header on 200/404/500, the file-handler scans and the health-poll rules.

SEAT_UNAVAILABLE at INFO with seat_conflicts_total and the pg_indexes check on request_id are the last two tests.
Not covered: "capturing stdout for a FULL TEST RUN" - the seven-key check runs over one real process's stdout.
"""

from __future__ import annotations

import json
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

from ..conftest import VALID_ENV
from ..test_health import failing_probe, ok_probe
from ._support import rg
from .test_s_xct_29 import _boot_env, _free_port, _refused

BACKEND_DIR = Path(__file__).resolve().parents[2]
SEVEN = {"timestamp", "level", "logger", "message", "service", "instance_id", "request_id"}
RID = re.compile(r"^[0-9a-f]{8}$")


def run_real_process(requests: list[tuple[str, str, dict]]) -> tuple[str, str, list[httpx.Response]]:
    """Boot `python -m app api` for real, send the requests, SIGTERM it, return (stdout, stderr, responses)."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app", "api"],
        cwd=BACKEND_DIR,
        env=_boot_env(API_PORT=str(port), DB_CONNECT_TIMEOUT_MS="200", REDIS_CONNECT_TIMEOUT_MS="100", REDIS_COMMAND_TIMEOUT_MS="100"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    responses = []
    try:
        for _ in range(200):  # a startup bound by count (200 x 0.1 s), never by a clock reading (S-SEA-08)
            if not _refused(port) or proc.poll() is not None:
                break
            time.sleep(0.1)
        for method, path, headers in requests:
            responses.append(httpx.request(method, f"http://127.0.0.1:{port}{path}", headers=headers, timeout=10))
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
    return out, err, responses


def test_every_stdout_line_of_a_real_process_is_json_with_the_seven_keys():
    out, err, rs = run_real_process(
        [("GET", "/health/live", {}), ("GET", "/no/such/page", {}), ("GET", "/health/ready", {}), ("GET", "/health/live", {"X-Request-Id": "injected-by-caller"})]
    )
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) >= 5, out
    parsed = [json.loads(ln) for ln in lines]  # json.loads raising IS the failure
    for p in parsed:
        assert SEVEN <= p.keys(), p
        assert RID.match(p["request_id"]), p
    assert err == ""
    assert [r.status_code for r in rs] == [200, 404, 503, 200]


def test_no_file_handler_and_no_log_file_opened():
    assert rg(r"FileHandler|RotatingFileHandler|WatchedFileHandler", "backend/app", "backend/migrations") == []
    assert rg(r"open\(.*\.log", "backend/app", "backend/migrations") == []


def _app(clock, probes=None):
    app = create_app(Settings(**VALID_ENV), clock=clock, probes=probes or [ok_probe("postgres"), ok_probe("redis")])

    @app.get("/_test/boom")
    async def boom():
        raise RuntimeError("boom")

    return app


def test_generated_id_is_in_the_header_on_a_200_a_404_and_a_500(valid_env, clock, log_capture):
    with TestClient(_app(clock), raise_server_exceptions=False) as c:
        rs = [c.get("/health/live"), c.get("/nope"), c.get("/_test/boom")]
    assert [r.status_code for r in rs] == [200, 404, 500]
    ids = [r.headers["x-request-id"] for r in rs]
    assert all(RID.match(i) for i in ids) and len(set(ids)) == 3
    assert rs[1].json()["error"]["request_id"] == ids[1]
    assert rs[2].json()["error"]["request_id"] == ids[2]


def test_injected_request_id_is_recorded_as_client_request_id_and_not_used(valid_env, clock, log_capture):
    with TestClient(_app(clock)) as c:
        r = c.get("/nope", headers={"X-Request-Id": "injected-by-caller"})
    done = [ln for ln in log_capture.lines() if ln["message"] == "request completed"]
    assert len(done) == 1
    assert done[0]["client_request_id"] == "injected-by-caller"
    assert RID.match(done[0]["request_id"]) and done[0]["request_id"] != "injected-by-caller"
    assert done[0]["request_id"] == r.headers["x-request-id"]
    assert {"route", "method", "status_code", "duration_ms"} <= done[0].keys()
    assert done[0]["level"] == "INFO"


def test_two_live_polls_write_no_info_line_and_a_ready_failure_writes_a_warning(valid_env, clock, log_capture):
    with TestClient(_app(clock, [failing_probe("postgres"), ok_probe("redis")])) as c:
        log_capture.stream.truncate(0)
        log_capture.stream.seek(0)
        c.get("/health/live")
        c.get("/health/live")
        # The test client's own `httpx` logger is not the application; every other logger counts.
        assert [ln for ln in log_capture.lines() if ln["level"] == "INFO" and ln["logger"] != "httpx"] == []
        c.get("/health/ready")
    levels = [ln["level"] for ln in log_capture.lines()]
    assert any(lv in ("WARNING", "ERROR", "CRITICAL") for lv in levels)


def test_request_id_is_never_a_join_key():
    assert rg(r"JOIN[^;]*request_id", "backend/app") == []


# ---- the Phase 4/7 clauses: a seat conflict at INFO with its counter, and no unique index on request_id ----------


import pytest  # noqa: E402


@pytest.mark.anyio
async def test_a_seat_unavailable_outcome_logs_info_no_warning_and_counts_a_conflict(migrated_db, log_capture):
    from app.core import metrics
    from tests.pay.kit import C1, api, book, clock_at, confirm, hold, user, world7

    world7(migrated_db)
    u, other = user(migrated_db), user(migrated_db)
    async with api(migrated_db, clock_at()) as c:
        lone = await hold(c, u, [C1])
        book(migrated_db, other, 7, [C1])  # the lock was won; the constraint decides
        before = sum(v for (n, _), v in metrics._counters.items() if n == "seat_conflicts_total")
        lost = await confirm(c, u, lone["hold_token"], key="k-xct24")
        after = sum(v for (n, _), v in metrics._counters.items() if n == "seat_conflicts_total")
    assert lost.status_code == 409 and lost.json()["error"]["code"] == "SEAT_UNAVAILABLE"
    lines = [ln for ln in log_capture.lines() if ln.get("request_id") == lost.headers["x-request-id"]]
    assert any(ln["message"] == "seat taken at confirm" and ln["level"] == "INFO" for ln in lines)
    assert not [ln for ln in lines if ln["level"] == "WARNING"]
    assert after == before + 1


def test_no_unique_index_carries_request_id(migrated_db):
    from tests.dbkit import owner_sql

    assert owner_sql(migrated_db, "SELECT count(*) FROM pg_indexes WHERE indexdef LIKE '%%request_id%%' "
                                  "AND indexdef LIKE 'CREATE UNIQUE INDEX%%'") == [(0,)]

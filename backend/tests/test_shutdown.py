"""P-XCT-17 / SRC-002 §7.5: on SIGTERM stop accepting, drain in-flight, run the release hooks, exit 0.

Phase 1 holds no locks. The hook list is what Phase 4 hangs the per-instance lock release on.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

from .conftest import VALID_ENV
from .test_health import ok_probe

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_shutdown_hooks_run_in_order_and_one_failure_does_not_stop_the_rest(valid_env, clock, log_capture):
    ran: list[str] = []
    app = create_app(Settings(**VALID_ENV), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])

    async def first():
        ran.append("first")

    async def broken():
        raise RuntimeError("release failed")

    async def last():
        ran.append("last")

    app.state.shutdown_hooks.extend([("first", first), ("broken", broken), ("last", last)])
    with TestClient(app):
        pass
    assert ran == ["first", "last"]
    errors = [ln for ln in log_capture.lines() if ln["level"] == "ERROR"]
    assert any(ln.get("hook") == "broken" for ln in errors)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_listening(port: int, deadline_s: float = 15.0) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("harness never started listening")


def test_sigterm_drains_an_in_flight_request_and_exits_zero():
    port = _free_port()
    env = dict(os.environ, **VALID_ENV, API_PORT=str(port), SHUTDOWN_DRAIN_TIMEOUT_SECONDS="10", PYTHONPATH=str(BACKEND_DIR))
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.drain_harness"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_listening(port)
        result: dict = {}

        def in_flight():
            r = httpx.get(f"http://127.0.0.1:{port}/_drain/slow?seconds=5", timeout=15)
            result["status"] = r.status_code
            result["body"] = r.json()

        lines: list[str] = []
        entered = threading.Event()

        def read_output():
            for line in proc.stdout:
                lines.append(line)
                if "drain handler entered" in line:
                    entered.set()

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        t = threading.Thread(target=in_flight)
        t.start()
        # Ordered by the harness's own signal, never by a sleep: the handler logs when it is entered.
        assert entered.wait(timeout=15), "the slow request never reached the handler"
        proc.send_signal(signal.SIGTERM)
        # stop accepting: a NEW connection after SIGTERM is refused - observed while the first request is
        # still in flight (it sleeps 5 s), so the refusal is the drain, not the process having exited.
        refused = False
        for _ in range(400):
            try:
                httpx.get(f"http://127.0.0.1:{port}/health/live", timeout=1)
            except httpx.ConnectError:
                refused = True
                break
            time.sleep(0.01)
        assert refused, "new connections were still accepted after SIGTERM"
        assert "status" not in result, "the in-flight request had already finished: the check proved nothing"
        t.join(timeout=15)
        code = proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
    reader.join(timeout=15)  # the reader ends at EOF, once the process has exited and its pipe is drained
    out = "".join(lines)
    assert result.get("status") == 200, out
    assert result["body"] == {"slept": 5.0}
    assert code == 0, out
    assert '"shutdown hooks complete"' in out

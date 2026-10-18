"""Shared test fixtures.

Time is injected everywhere (CLAUDE.md: "a test that reads the wall clock is a defect"). FakeClock is
the only clock a test ever hands to the application.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

# Every variable the Phase 1 Settings class knows about. Tests clear all of them first so a value
# exported on the machine running the tests can never leak into an assertion.
PHASE1_VARS = (
    "DATABASE_URL",
    "REDIS_URL",
    "LOG_LEVEL",
    "API_PORT",
    "DB_CONNECT_TIMEOUT_MS",
    "REDIS_CONNECT_TIMEOUT_MS",
    "REDIS_COMMAND_TIMEOUT_MS",
    "SHUTDOWN_DRAIN_TIMEOUT_SECONDS",
    "READINESS_CACHE_TTL_SECONDS",
)

VALID_ENV = {
    "DATABASE_URL": "postgresql://user:pw@db.invalid:5432/frontrow",
    "REDIS_URL": "redis://cache.invalid:6379/0",
}


class FakeClock:
    """A clock that moves only when a test moves it."""

    def __init__(self) -> None:
        self._mono = 1000.0
        self._now = datetime(2026, 10, 18, 9, 30, 0, 123000, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self._mono

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in PHASE1_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def valid_env(clean_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for k, v in VALID_ENV.items():
        clean_env.setenv(k, v)
    return clean_env


class LogCapture:
    """Captures what the application's JSON handler writes, line by line."""

    def __init__(self) -> None:
        self.stream = io.StringIO()

    def lines(self) -> list[dict]:
        raw = [ln for ln in self.stream.getvalue().splitlines() if ln.strip()]
        return [json.loads(ln) for ln in raw]  # json.loads raising IS the failure we want

    def raw_lines(self) -> list[str]:
        return [ln for ln in self.stream.getvalue().splitlines() if ln.strip()]


@pytest.fixture
def log_capture(clock: FakeClock):
    from app.core.logging import configure_logging

    cap = LogCapture()
    configure_logging(level="INFO", service="api", instance_id="test0001", now=clock.now, stream=cap.stream)
    yield cap
    logging.getLogger().handlers.clear()

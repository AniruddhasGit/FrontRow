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

# Every variable the Settings models declare. Tests clear all of them first so a value exported on
# the machine running the tests can never leak into an assertion. Derived from the models, so a new
# setting cannot be forgotten here.
from app.core.config import Settings  # noqa: E402

# The seed's own three (scripts/seed.py SEED_VARIABLES), which no Settings model declares (S-XCT-48).
SEED_VARIABLES = ("SEED_DEFAULT_PASSWORD", "SEED_CHANGEOVER_MINUTES", "SEED_EMAIL_DOMAIN")
PHASE1_VARS = tuple(Settings.model_fields) + SEED_VARIABLES

# A complete, valid environment for the variables with no default (PRD S7.9). Every value is an
# obvious test placeholder: .invalid hosts never resolve, and no value is a real credential.
VALID_ENV = {
    "DATABASE_URL": "postgresql://user:pw@db.invalid:5432/frontrow",
    "REDIS_URL": "redis://cache.invalid:6379/0",
    "QUEUE_URL": "http://queue.invalid:9324/000000000000/frontrow-receipts",
    "JWT_SECRET": "test-only-signing-secret-not-a-real-one",
    "PAYMENT_PROVIDER": "simulated",
    "MAIL_PROVIDER": "stub",
    "S3_BUCKET_NAME": "frontrow-posters-test",
    "AWS_REGION": "ap-south-1",
    "SES_SENDER_ADDRESS": "receipts@example.invalid",
    "PUBLIC_BASE_URL": "http://localhost:8080",
    "COOKIE_SECURE": "false",
    "FORWARDED_ALLOW_IPS": "127.0.0.1",
    "PAYMENT_SIMULATOR_FAIL_KEY_PREFIX": "test-fail-",
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


# Database fixtures for every lane (tests/dbkit.py). Imported here so pytest registers them.
from .dbkit import anyio_backend, create_database, drop_database  # noqa: E402,F401


@pytest.fixture(scope="module")
def migrated_db():
    """One throwaway migrated database per test module - the shared fixture every module whose database holds a
    booking uses. Its teardown (drop_database) asserts S-SCP-14: no booking with a cancellation instant and no status
    but 'confirmed', and a violation fails the module."""
    db = create_database(migrate=True)
    yield db
    try:
        # S-ADM-02: "SELECT count(*) FROM audit_log WHERE actor_user_id IS NULL returns 0 after the whole suite has run".
        # Every module has its own database, so the suite's audit rows are the union of these; each is checked last.
        from tests.dbkit import owner_sql
        assert owner_sql(db, "SELECT count(*) FROM audit_log WHERE actor_user_id IS NULL") == [(0,)]
    finally:
        drop_database(db)

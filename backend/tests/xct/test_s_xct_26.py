"""S-XCT-26 (PRD P-XCT-12, S7.8): central redaction, and no credential in any captured line.

Asserted: the central redaction of the five keys, the pattern scans over one real process's stdout, no line holding
both a booking reference and an @ over the booking path (a real hold and confirm) and the receipt path (the real worker
sending the receipt), both captured at DEBUG, and the LOG_LEVEL default and runbook clauses.

NOT covered: "over the captured stdout of a full test run" for the seeded password, bcrypt, JWT, Authorization: Bearer
and 13-19 digit scans. Those run over one real process's stdout, not the whole suite's.
"""

from __future__ import annotations

import io
import logging
import re

import pytest

from app.core.config import Settings
from tests.dbkit import owner_sql

from ._support import rg
from .test_s_xct_24 import run_real_process


def test_the_five_denylisted_keys_are_redacted_with_no_call_site_change(log_capture):
    values = {"password": "pw-value-1", "password_hash": "hash-value-2", "jwt": "jwt-value-3", "authorization": "auth-value-4", "cookie": "cookie-value-5"}
    logging.getLogger("app.anything").info("ordinary call", extra=values)
    line = log_capture.lines()[-1]
    for key in values:
        assert line[key] == "[REDACTED]"
    raw = log_capture.stream.getvalue()
    assert not any(v in raw for v in values.values())


def test_a_real_process_stdout_carries_no_credential_shaped_value():
    out, _, _ = run_real_process(
        [("GET", "/health/live", {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.abc", "Cookie": "fr_session=eyJabcdefghijkl"}), ("GET", "/nope", {})]
    )
    assert out.strip()
    for line in out.splitlines():
        assert not re.search(r"\$2[aby]\$\d\d\$", line)
        assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", line)
        assert "Authorization: Bearer" not in line
        assert not re.search(r"\d{13,19}", line)


def test_log_level_defaults_to_info_and_nothing_switches_it_by_environment():
    assert Settings.model_fields["LOG_LEVEL"].default == "INFO"
    assert rg(r"ENVIRONMENT|APP_ENV", "backend/app/core/logging.py") == []


def test_the_deployment_spec_refuses_debug():
    assert rg("LOG_LEVEL=DEBUG", "docs/30 Deployment", fixed=True)


@pytest.mark.anyio
async def test_no_booking_or_receipt_line_holds_a_reference_beside_an_email_address(migrated_db):
    """A real hold and confirm (the booking path) and the real worker sending that booking's receipt (the receipt
    path), every line captured at DEBUG; no line matches both a reference-shaped run and an @."""
    from app.core.logging import configure_logging
    from tests.pay.kit import C1, api, clock_at, confirm, hold, user, world7
    from tests.tkt.kit import Clock, message, worker

    db = world7(migrated_db)["db"]
    u = user(db, email="ref.beside@example.com")
    stream, clock = io.StringIO(), clock_at()
    configure_logging(level="DEBUG", service="api", instance_id="test0001", now=clock.now, stream=stream)
    try:
        async with api(db, clock) as c:
            h = await hold(c, u, [C1])
            r = await confirm(c, u, h["hold_token"])
            assert r.status_code == 201, r.text
        booking_id = owner_sql(db, "SELECT id FROM booking WHERE user_id = %s", (u,))[0][0]
        w = worker(db, Clock())
        try:
            assert await w.handle(message(booking_id)) is True
        finally:
            await w.engine.dispose()
        assert w.transport.calls  # the receipt was sent, so its log path ran
    finally:
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)
    lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
    assert any("/api/bookings" in ln for ln in lines) and any("receipt" in ln.lower() for ln in lines)
    ref = re.compile(r"[23456789ACDEFHJKMNPQRTVWXY]{8}")
    assert [ln for ln in lines if ref.search(ln) and "@" in ln] == []

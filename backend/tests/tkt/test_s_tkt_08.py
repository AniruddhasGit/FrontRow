"""S-TKT-08 (P-TKT-05): the SES call is bounded; a timed-out send is failed and retryable, and so is a refusal."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from tests.conftest import VALID_ENV
from tests.tkt.kit import Clock, Mail, booking, message, owner_sql, truncate, worker

pytestmark = pytest.mark.anyio
BACKEND = Path(__file__).resolve().parents[2]
WORKERS = BACKEND / "app" / "workers"


@pytest.fixture
def db(migrated_db):
    truncate(migrated_db)
    return migrated_db


def _row(db, b):
    return owner_sql(db, "SELECT status, sent_at, ses_message_id, last_error FROM receipt_dispatch WHERE booking_id = %s", (b,))[0]


@pytest.mark.parametrize("ms", ["5000", "1200"])
async def test_a_blocked_send_is_abandoned_at_exactly_the_configured_bound(db, ms):
    clock = Clock()
    t = clock.now()
    b = booking(db)
    mail = Mail()
    mail.block = True
    w = worker(db, clock, mail=mail, SES_SEND_TIMEOUT_MS=ms)
    w.queue.held.append(m := message(b))
    try:
        await w.turn()
        assert w.within.abandoned_at == [t + timedelta(milliseconds=int(ms))]
        status, sent_at, mid, last_error = _row(db, b)
        assert (status, sent_at, mid) == ("failed", None, None)
        assert "timeout" in last_error and Mail.REFUSAL not in last_error
        assert [x.id for x in w.queue.held] == [m.id]  # not deleted
        # The redelivery claims the failed row and makes a SECOND call - asserted as made, not prevented.
        mail.block = False
        await w.turn()
    finally:
        await w.engine.dispose()
    assert len(mail.calls) == 2 and _row(db, b)[0] == "sent"


async def test_a_refusal_is_failed_with_the_providers_own_words(db):
    b = booking(db)
    mail = Mail()
    mail.refuse = True
    w = worker(db, Clock(), mail=mail)
    try:
        assert await w.handle(message(b)) is False
    finally:
        await w.engine.dispose()
    status, sent_at, mid, last_error = _row(db, b)
    assert (status, sent_at, mid) == ("failed", None, None) and Mail.REFUSAL in last_error and "timeout" not in last_error


def test_the_bound_is_read_from_configuration_and_not_typed():
    hits = [f"{p.name}:{i}" for p in WORKERS.rglob("*.py") for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if "5000" in ln]
    assert hits == []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("missing", ["MAIL_PROVIDER", "SES_SENDER_ADDRESS"])
@pytest.mark.parametrize("command", ["api", "worker"])
def test_the_process_refuses_to_start_without_a_mail_provider_or_sender(tmp_path, missing, command):
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({**VALID_ENV, "API_PORT": str(port), "PYTHONPATH": str(BACKEND)})
    del env[missing]
    proc = subprocess.run([sys.executable, "-m", "app", command], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 78 and missing in proc.stdout
    with socket.socket() as s:  # nothing is listening: the port was never bound
        assert s.connect_ex(("127.0.0.1", port)) != 0
    assert re.search(r'"service":"%s"' % command, proc.stdout)


async def test_an_unexpected_error_after_the_claim_releases_it_at_once(db):
    """Not a refusal, not a timeout: a transport bug. The claim must not sit in `sending` for the stale age - the row
    goes back to `failed` (retryable) and the message stays, so the next delivery sends without waiting 900 s."""
    b = booking(db)
    mail = Mail()

    async def broken(to, message):
        raise ValueError("unexpected transport bug (test)")

    mail.send = broken
    w = worker(db, Clock(), mail=mail)
    try:
        assert await w.handle(message(b)) is False
        status, sent_at, _, last_error = _row(db, b)
        assert (status, sent_at) == ("failed", None) and "ValueError" in last_error
        mail.send = Mail().send  # fixed: the redelivery is claimed at once, with no clock movement
        assert await w.handle(message(b)) is True
    finally:
        await w.engine.dispose()
    assert _row(db, b)[0] == "sent"

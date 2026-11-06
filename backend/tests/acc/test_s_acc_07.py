"""S-ACC-07 - send a single-use reset link and answer identically for an unknown address (P-ACC-07, EP-ACC-05).

The queue is a recording stub installed as app.state.reset_queue (app/server.py installs the real one). The relay is
never started here, so every message the stub records was sent by the request itself. Time is injected (SetClock).
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.logging import configure_logging
from app.domain import accounts
from app.workers import Worker, render
from tests.acc._support import SetClock, api, flush_redis, settings_for
from tests.conftest import VALID_ENV
from tests.dbkit import app_sql, insert_user
from tests.tkt.kit import Queue

pytestmark = pytest.mark.anyio

T10 = datetime(2026, 8, 14, 10, 0, 0, tzinfo=timezone.utc)
SENT_30 = ("If that email address has an account, a reset link is on its way to it. "
           "The link works once and expires in 30 minutes.")
BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


@pytest.fixture
def at10():
    c = SetClock()
    c.set(T10)
    return c


class Sends:
    def __init__(self, fail: bool = False) -> None:
        self.bodies: list[dict] = []
        self.fail = fail

    async def __call__(self, body: dict) -> None:
        self.bodies.append(body)
        if self.fail:
            raise ConnectionError("queue unreachable (stub)")


async def _request(c, email: str, sends: Sends | None = None):
    c.application.state.reset_queue = sends if sends is not None else Sends()
    return await c.post("/api/auth/password-reset/request", json={"email": email})


async def test_known_and_unknown_addresses_get_byte_identical_202_bodies(migrated_db, at10):
    insert_user(migrated_db, role="customer", email="known@example.com")
    async with api(settings_for(migrated_db), at10) as c:
        known = await _request(c, "known@example.com")
        unknown = await _request(c, "nobody@example.com")
    assert (known.status_code, unknown.status_code) == (202, 202)
    assert known.content == unknown.content
    assert known.json() == {"message": SENT_30}


async def test_the_minutes_follow_the_setting_on_the_body_and_in_the_email(migrated_db, at10):
    user = insert_user(migrated_db, role="customer", email="ten@example.com")
    settings = settings_for(migrated_db, PASSWORD_RESET_TTL_SECONDS="600")
    async with api(settings, at10) as c:
        r = await _request(c, "ten@example.com")
    assert r.json()["message"].endswith("The link works once and expires in 10 minutes.")
    email = render.password_reset("ten@example.com", "T" * 43, settings).get_body(("plain",)).get_content()
    assert "The link works once and expires in 10 minutes." in email
    assert user


async def test_two_requests_leave_exactly_one_live_token_and_the_first_marked_used(migrated_db, at10):
    user = insert_user(migrated_db, role="customer", email="twice@example.com")
    async with api(settings_for(migrated_db), at10) as c:
        await _request(c, "twice@example.com")
        await _request(c, "twice@example.com")
    assert app_sql(migrated_db, "SELECT count(*) FROM password_reset_token WHERE user_id = %s AND used_at IS NULL", (user,)) == [(1,)]
    assert app_sql(migrated_db, "SELECT count(*) FROM password_reset_token WHERE user_id = %s", (user,)) == [(2,)]


async def test_only_the_hash_is_stored_and_the_token_rides_in_the_queue_message_alone(migrated_db, at10, monkeypatch):
    user = insert_user(migrated_db, role="customer", email="hash@example.com")
    token = "Q" * 21 + "-_" + "z" * 20  # 43 URL-safe characters, stubbed generator
    monkeypatch.setattr(accounts, "new_reset_token", lambda: token)
    stream = io.StringIO()
    configure_logging(level="DEBUG", service="api", instance_id="test0001", now=at10.now, stream=stream)
    sends = Sends()
    try:
        async with api(settings_for(migrated_db, LOG_LEVEL="DEBUG"), at10) as c:
            r = await _request(c, "hash@example.com", sends)
    finally:
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)
    captured = stream.getvalue()
    assert "/api/auth/password-reset/request" in captured  # the capture covered the request
    [(token_id, digest, created, expires)] = app_sql(
        migrated_db, "SELECT id, token_sha256, created_at, expires_at FROM password_reset_token WHERE user_id = %s", (user,))
    assert digest == hashlib.sha256(token.encode()).hexdigest()
    assert (created, expires) == (T10, T10 + timedelta(seconds=1800))
    [(row_text,)] = app_sql(migrated_db, "SELECT password_reset_token::text FROM password_reset_token WHERE user_id = %s", (user,))
    assert token not in row_text and token not in r.text and token not in captured
    # The outbox row: the four keys, no token.
    [(payload, payload_text, status)] = app_sql(
        migrated_db, "SELECT payload, payload::text, status FROM outbox_message WHERE (payload->>'user_id')::bigint = %s", (user,))
    assert set(payload) == {"message_version", "request_id", "reset_token_id", "user_id"}
    assert token not in payload_text
    # Exactly one message, sent by the request, with the five keys and the token.
    assert len(sends.bodies) == 1
    body = sends.bodies[0]
    assert set(body) == {"message_version", "request_id", "reset_token", "reset_token_id", "user_id"}
    assert body["reset_token"] == token and hashlib.sha256(body["reset_token"].encode()).hexdigest() == digest
    assert (body["reset_token_id"], body["user_id"]) == (token_id, user)
    assert status == "sent"


async def test_a_rolled_back_transaction_leaves_no_token_no_outbox_row_and_no_send(migrated_db, at10, monkeypatch):
    user = insert_user(migrated_db, role="customer", email="rollback@example.com")

    def boom(token: str) -> str:
        raise RuntimeError("forced failure inside the reset transaction")

    # token_digest runs inside the transaction, after the earlier-token UPDATE and before the INSERTs.
    monkeypatch.setattr(accounts, "token_digest", boom)
    sends = Sends()
    async with api(settings_for(migrated_db), at10) as c:
        r = await _request(c, "rollback@example.com", sends)
    assert r.status_code == 500
    assert app_sql(migrated_db, "SELECT count(*) FROM password_reset_token WHERE user_id = %s", (user,)) == [(0,)]
    assert app_sql(migrated_db, "SELECT count(*) FROM outbox_message WHERE (payload->>'user_id')::bigint = %s", (user,)) == [(0,)]
    assert sends.bodies == []


async def test_a_failed_send_still_answers_202_leaves_the_row_pending_and_the_relay_never_sends_it(migrated_db, at10):
    user = insert_user(migrated_db, role="customer", email="fail@example.com")
    settings = settings_for(migrated_db)
    async with api(settings, at10) as c:
        ok = await _request(c, "nobody-else@example.com")
        failed = await _request(c, "fail@example.com", Sends(fail=True))
        engine = c.application.state.db_engine
        queue = Queue()
        at10.advance(3600)  # far past OUTBOX_RELAY_MIN_AGE_SECONDS
        await Worker(settings, at10, engine, queue, None).relay()
    assert failed.status_code == 202 and failed.content == ok.content
    assert app_sql(migrated_db, "SELECT status FROM outbox_message WHERE (payload->>'user_id')::bigint = %s", (user,)) == [("pending",)]
    assert [t for t, _ in queue.sent if t == "password_reset.send"] == []


async def test_an_unknown_address_writes_nothing_and_sends_nothing(migrated_db, at10):
    sends = Sends()
    counts = "SELECT (SELECT count(*) FROM password_reset_token), (SELECT count(*) FROM outbox_message)"
    before = app_sql(migrated_db, counts)
    async with api(settings_for(migrated_db), at10) as c:
        r = await _request(c, "ghost@example.com", sends)
    assert r.status_code == 202
    assert app_sql(migrated_db, counts) == before
    assert sends.bodies == []


@pytest.mark.parametrize("email", ["", "   ", "not-an-address", None])
async def test_an_empty_or_malformed_address_is_422_enter_an_email_address(migrated_db, at10, email):
    async with api(settings_for(migrated_db), at10) as c:
        r = await c.post("/api/auth/password-reset/request", json={"email": email})
    assert r.status_code == 422
    assert (r.json()["error"]["code"], r.json()["error"]["message"]) == ("VALIDATION_FAILED", "Enter an email address.")


def test_the_process_refuses_to_start_without_public_base_url_and_names_it_on_stderr(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({k: v for k, v in VALID_ENV.items() if k != "PUBLIC_BASE_URL"})
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "PUBLIC_BASE_URL" in proc.stderr

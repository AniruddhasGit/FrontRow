"""S-TKT-15 (P-TKT-12): the password-reset email is sent exactly once per request.

The worker clauses run the real Worker with stubbed queue and mail ports. The enqueue clauses run end to end in
test_the_stubbed_token_rides_only_in_the_message_and_the_link: EP-ACC-05 with the token generator stubbed to
TESTTOKENVALUE0001, then the worker on the message the request sent, with stdout captured at DEBUG for both."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.dbkit import insert_user
from tests.tkt.kit import Clock, Mail, Queue, owner_sql, reset_message, reset_token, truncate, worker

pytestmark = pytest.mark.anyio


@pytest.fixture
def db(migrated_db):
    truncate(migrated_db)
    return migrated_db


def _cols(db, t):
    return owner_sql(db, "SELECT email_claimed_at, email_sent_at FROM password_reset_token WHERE id = %s", (t,))[0]


async def _deliver(db, clock, msg, mail, queue=None, **settings):
    w = worker(db, clock, queue=queue, mail=mail, RECEIPT_CLAIM_STALE_SECONDS="900", **settings)
    try:
        return await w.handle(msg)
    finally:
        await w.engine.dispose()


async def test_two_deliveries_make_one_call_and_the_link_carries_the_token(db):
    clock, mail = Clock(), Mail()
    u = insert_user(db, role="customer", email="customer@example.invalid")
    t = reset_token(db, u, clock)
    m = reset_message(t, u)
    assert await _deliver(db, clock, m, mail) is True
    assert await _deliver(db, clock, m, mail) is True
    assert len(mail.calls) == 1
    claimed, sent = _cols(db, t)
    assert claimed is not None and sent is not None
    to, msg = mail.calls[0]
    body = msg.get_body(("plain",)).get_content()
    assert to == "customer@example.invalid"
    assert "https://example.invalid/account/reset/confirm#token=TESTTOKENVALUE0001\n" in body
    assert "expires in 30 minutes" in body  # 1800 / 60, interpolated


@pytest.mark.parametrize("age,calls", [(120, 0), (901, 1)])
async def test_a_dead_workers_claim_is_retaken_only_once_stale(db, age, calls):
    clock, mail = Clock(), Mail()
    u = insert_user(db, role="customer")
    t = reset_token(db, u, clock, email_claimed_at=clock.now())
    clock.advance(age)
    assert await _deliver(db, clock, reset_message(t, u), mail) is True
    assert len(mail.calls) == calls


@pytest.mark.parametrize("fault", ["refuse", "block"])
async def test_a_refusal_or_a_timeout_releases_the_claim_and_the_next_delivery_sends(db, fault):
    clock, mail = Clock(), Mail()
    u = insert_user(db, role="customer")
    t = reset_token(db, u, clock)
    setattr(mail, fault, True)
    assert await _deliver(db, clock, reset_message(t, u), mail) is False  # not deleted
    assert _cols(db, t) == (None, None)
    setattr(mail, fault, False)
    clock.advance(1)
    assert await _deliver(db, clock, reset_message(t, u), mail) is True
    assert len(mail.calls) == 2 and _cols(db, t)[1] is not None


async def test_three_refused_deliveries_make_three_calls_delete_nothing_and_send_nothing_to_any_queue(db):
    clock, mail, queue = Clock(), Mail(), Queue()
    mail.refuse = True
    u = insert_user(db, role="customer")
    t = reset_token(db, u, clock)
    # The same outbox row a reset request leaves pending: the relay must never send it (SRC-004 R-3).
    owner_sql(db, "INSERT INTO outbox_message (topic, payload, status, attempts, created_at) VALUES ('password_reset.send', "
                  "%s::jsonb, 'pending', 0, %s)", ('{"user_id": %d, "reset_token_id": %d, "request_id": "a1b2c3d4", '
                                                  '"message_version": 1}' % (u, t), clock.now() - timedelta(hours=1)))
    m = reset_message(t, u)
    w = worker(db, clock, queue=queue, mail=mail)
    queue.held.append(m)
    try:
        for _ in range(3):
            clock.advance(1)
            await w.turn()
    finally:
        await w.engine.dispose()
    assert len(mail.calls) == 3 and queue.deleted == [] and queue.sent == []
    assert owner_sql(db, "SELECT status FROM outbox_message WHERE topic = 'password_reset.send'") == [("pending",)]


async def test_a_redelivery_a_day_after_the_send_makes_no_call(db):
    clock, mail = Clock(), Mail()
    u = insert_user(db, role="customer")
    t = reset_token(db, u, clock)
    assert await _deliver(db, clock, reset_message(t, u), mail) is True
    clock.advance(24 * 3600)
    assert await _deliver(db, clock, reset_message(t, u), mail) is True
    assert len(mail.calls) == 1


async def test_the_booking_deletion_rule_is_not_applied_to_a_reset(db):
    """A reset message survives a worker in which every booking lookup fails: the refused send leaves it held."""
    clock, mail = Clock(), Mail()
    mail.refuse = True
    u = insert_user(db, role="customer")
    t = reset_token(db, u, clock)
    owner_sql(db, "TRUNCATE booking_seat, booking, receipt_dispatch CASCADE")
    assert await _deliver(db, clock, reset_message(t, u), mail) is False


async def test_the_stub_line_carries_neither_the_token_nor_the_address(db):
    import io
    from app.domain.mail import StubTransport
    from app.workers.render import password_reset
    from tests.tkt.kit import app_settings
    out, to = io.StringIO(), "reset.me@example.invalid"
    await StubTransport(out).send(to, password_reset(to, "Tok_en-123abc", app_settings(db, PUBLIC_BASE_URL="https://example.invalid")))
    assert "Tok_en-123abc" not in out.getvalue() and "reset.me@example.invalid" not in out.getvalue()
    assert "token=[REDACTED]" in out.getvalue()


async def test_the_stubbed_token_rides_only_in_the_message_and_the_link(db, monkeypatch, capsys):
    import io
    import logging
    import uuid

    from app.core.logging import configure_logging
    from app.domain import accounts
    from app.workers.queue import Message
    from tests.acc._support import api, flush_redis, settings_for

    token = "TESTTOKENVALUE0001"
    monkeypatch.setattr(accounts, "new_reset_token", lambda: token)
    flush_redis()
    clock, mail = Clock(), Mail()
    u = insert_user(db, role="customer", email="reset.e2e@example.invalid")
    sent: list[dict] = []

    async def record(body: dict) -> None:
        sent.append(body)

    stream = io.StringIO()
    configure_logging(level="DEBUG", service="api", instance_id="test0001", now=clock.now, stream=stream)
    try:
        async with api(settings_for(db, LOG_LEVEL="DEBUG"), clock) as c:
            c.application.state.reset_queue = record
            r = await c.post("/api/auth/password-reset/request", json={"email": "reset.e2e@example.invalid"})
        assert r.status_code == 202, r.text
        [body] = sent
        msg = Message(id=uuid.uuid4().hex, topic="password_reset.send", body=body, receipt_handle=uuid.uuid4().hex)
        assert await _deliver(db, clock, msg, mail, LOG_LEVEL="DEBUG") is True
    finally:
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)
    stdout = stream.getvalue() + capsys.readouterr().out
    assert "/api/auth/password-reset/request" in stdout  # the capture covered the request
    assert set(body) == {"message_version", "request_id", "reset_token", "reset_token_id", "user_id"}
    assert body["reset_token"] == token and body["user_id"] == u
    [(_, email)] = mail.calls
    link = [ln for ln in email.get_body(("plain",)).get_content().splitlines() if "token=" in ln]
    assert link and link[0].endswith("token=TESTTOKENVALUE0001")
    outbox = " ".join(t for (t,) in owner_sql(db, "SELECT payload::text FROM outbox_message"))
    tokens = " ".join(t for (t,) in owner_sql(db, "SELECT password_reset_token::text FROM password_reset_token"))
    assert outbox and tokens
    assert token not in outbox and token not in tokens and token not in stdout

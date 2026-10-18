"""S-TKT-15 (P-TKT-12): the password-reset email is sent exactly once per request - the worker half.

The enqueue half (EP-ACC-05 putting the message on the queue at request time, with the token generator stubbed) is the
account lane's endpoint, which does not exist yet; those clauses are not asserted here."""

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

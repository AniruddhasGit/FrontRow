"""S-TKT-05 (P-TKT-04): the receipt_dispatch and outbox rows commit with the booking, or neither exists."""

from __future__ import annotations

import json

import psycopg
import pytest

from app.domain import reference as refs
from tests.pay.kit import F7, F8, api, clock_at, confirm, count, hold, owner_sql, user, world7
from tests.tkt.kit import Clock, Queue, worker

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def _book(db, seats=(F7,), observer=None, draw=None):
    u = user(db)
    async with api(db, clock_at()) as c:
        if observer:
            c.application.state.confirm_observer = observer
        if draw:
            c.application.state.draw_reference = draw
        h = await hold(c, u, list(seats))
        return await confirm(c, u, h["hold_token"])


def _insert(db, topic: str, payload: dict):
    with psycopg.connect(db.app_url, autocommit=True) as conn:
        conn.execute("INSERT INTO outbox_message (topic, payload, status, attempts) VALUES (%s, %s::jsonb, 'pending', 0)",
                     (topic, json.dumps(payload)))


async def test_one_confirm_writes_one_pending_dispatch_row_and_one_pending_outbox_row(world):
    db = world["db"]
    r = await _book(db)
    assert r.status_code == 201, r.text
    b = r.json()["booking_id"]
    assert owner_sql(db, "SELECT status, dispatch_seq, attempts, claimed_at, sent_at, ses_message_id, last_error FROM receipt_dispatch "
                         "WHERE booking_id = %s", (b,)) == [("pending", 1, 0, None, None, None, None)]
    assert owner_sql(db, "SELECT topic, status, attempts FROM outbox_message WHERE payload->>'booking_id' = %s", (str(b),)) == [
        ("receipt.send", "pending", 0)]
    (payload,), = owner_sql(db, "SELECT payload::text FROM outbox_message WHERE payload->>'booking_id' = %s", (str(b),))
    assert sorted(json.loads(payload)) == ["booking_id", "dispatch_seq", "message_version", "request_id"]
    assert "@" not in payload and "F7" not in payload and str(r.json()["total_paise"]) not in payload


@pytest.mark.parametrize("topic,payload", [
    ("receipt.render", {"booking_id": 1, "dispatch_seq": 1, "message_version": 1, "request_id": "a1b2c3d4"}),
    ("receipt.send", {"booking_id": 1, "dispatch_seq": 1, "message_version": 1, "request_id": "a1b2c3d4", "email": "x"}),
    ("receipt.send", {"booking_id": 1, "dispatch_seq": 1, "request_id": "a1b2c3d4"}),
])
def test_a_bad_topic_or_payload_shape_does_not_commit(world, topic, payload):
    db = world["db"]
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(db, topic, payload)
    assert count(db, "SELECT count(*) FROM outbox_message WHERE topic = 'receipt.render'") == 0
    assert count(db, "SELECT count(*) FROM outbox_message") == 0


async def test_a_reset_payload_commits_with_its_four_keys_never_with_the_token_and_is_never_relayed(world):
    db = world["db"]
    reset = {"message_version": 1, "request_id": "a1b2c3d4", "reset_token_id": 1, "user_id": 1}
    _insert(db, "password_reset.send", reset)
    assert count(db, "SELECT count(*) FROM outbox_message WHERE topic = 'password_reset.send'") == 1
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(db, "password_reset.send", {**reset, "reset_token": "TESTTOKENVALUE0001"})
    assert count(db, "SELECT count(*) FROM outbox_message WHERE topic = 'password_reset.send'") == 1
    owner_sql(db, "UPDATE outbox_message SET created_at = created_at - interval '1 hour'")
    q = Queue()
    w = worker(db, Clock("2030-01-01T00:00:00Z"), queue=q)
    try:
        await w.relay()
    finally:
        await w.engine.dispose()
    assert [t for t, _ in q.sent if t == "password_reset.send"] == []
    assert owner_sql(db, "SELECT status FROM outbox_message WHERE topic = 'password_reset.send'") == [("pending",)]


async def test_a_failed_outbox_insert_leaves_no_booking_and_no_seat(world):
    db = world["db"]
    ref = "7K3MQP4" + refs.check_character("7K3MQP4")

    def observer(step):
        if step == "outbox_message insert":
            raise RuntimeError("outbox insert forced to fail")

    r = await _book(db, observer=observer, draw=lambda: ref)
    assert r.status_code == 500
    assert count(db, "SELECT count(*) FROM booking WHERE reference = %s", (ref,)) == 0
    assert count(db, "SELECT count(*) FROM booking_seat WHERE showtime_id = 7") == 0


async def test_a_second_dispatch_row_for_one_booking_does_not_commit(world):
    db = world["db"]
    b = (await _book(db, seats=(F8,))).json()["booking_id"]
    with pytest.raises(psycopg.errors.UniqueViolation), psycopg.connect(db.app_url, autocommit=True) as conn:
        conn.execute("INSERT INTO receipt_dispatch (booking_id, status, dispatch_seq, attempts) VALUES (%s, 'pending', 1, 0)", (b,))
    assert count(db, "SELECT count(*) FROM receipt_dispatch WHERE booking_id = %s", (b,)) == 1

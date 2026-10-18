"""S-TKT-10 (P-TKT-07, EP-TKT-02): the owner re-sends a receipt; a request with nothing to send is refused at no cost."""

from __future__ import annotations

import pytest

from tests.brw.kit import without_request_id
from tests.dbkit import insert_user
from tests.pay.kit import api, clock_at, cookies, count, flush
from tests.tkt.kit import EMAIL, Clock, booking, message, owner_sql, set_claim, truncate, worker

pytestmark = pytest.mark.anyio
URL = "/api/bookings/by-reference/FR-ACDE-FHJD/resend-receipt"


@pytest.fixture
def world(migrated_db):
    truncate(migrated_db)
    flush()
    b = booking(migrated_db)
    owner = owner_sql(migrated_db, "SELECT user_id FROM booking WHERE id = %s", (b,))[0][0]
    return migrated_db, b, owner


def _dispatch(db, b):
    return owner_sql(db, "SELECT dispatch_seq, status FROM receipt_dispatch WHERE booking_id = %s", (b,))[0]


async def test_a_sent_receipt_is_queued_again_with_the_next_sequence(world):
    db, b, owner = world
    set_claim(db, b, "sent")
    audit = count(db, "SELECT count(*) FROM audit_log")
    async with api(db, clock_at()) as c:
        r = await c.post(URL, cookies=cookies(c, owner))
    assert r.status_code == 202 and r.json() == {"queued": True, "email_address": EMAIL}
    assert _dispatch(db, b) == (2, "pending")
    assert owner_sql(db, "SELECT (payload->>'dispatch_seq')::int FROM outbox_message WHERE (payload->>'booking_id')::bigint = %s", (b,)) == [(2,)]
    assert count(db, "SELECT count(*) FROM audit_log") == audit
    # A message still carrying dispatch_seq 1 after the row reached 2 sends nothing.
    w = worker(db, Clock())
    try:
        assert await w.handle(message(b, dispatch_seq=1)) is True
    finally:
        await w.engine.dispose()
    assert w.transport.calls == []


async def test_a_first_receipt_not_yet_attempted_enqueues_nothing_and_spends_no_token(world):
    db, b, owner = world
    async with api(db, clock_at()) as c:
        r = await c.post(URL, cookies=cookies(c, owner))
        assert r.status_code == 202 and r.json() == {"queued": False, "email_address": EMAIL}
        assert _dispatch(db, b) == (1, "pending") and count(db, "SELECT count(*) FROM outbox_message") == 0
        set_claim(db, b, "sent")
        # Accepted at once: the refusal above spent no per-booking interval token.
        assert (await c.post(URL, cookies=cookies(c, owner))).json()["queued"] is True


@pytest.mark.parametrize("status,claimed", [("sending", True), ("pending", True)])
async def test_a_resend_already_in_flight_enqueues_nothing(world, status, claimed):
    db, b, owner = world
    set_claim(db, b, status, clock_at().now())
    async with api(db, clock_at()) as c:
        r = await c.post(URL, cookies=cookies(c, owner))
    assert r.status_code == 202 and r.json()["queued"] is False and count(db, "SELECT count(*) FROM outbox_message") == 0


async def test_a_suppressed_row_is_refused_every_time_and_changes_nothing(world):
    db, b, owner = world
    set_claim(db, b, "suppressed")
    before = owner_sql(db, "SELECT * FROM receipt_dispatch WHERE booking_id = %s", (b,))
    async with api(db, clock_at()) as c:
        for _ in range(100):
            r = await c.post(URL, cookies=cookies(c, owner))
            assert r.status_code == 409 and r.json()["error"]["code"] == "RECEIPT_SUPPRESSED"
        assert owner_sql(db, "SELECT * FROM receipt_dispatch WHERE booking_id = %s", (b,)) == before
        assert count(db, "SELECT count(*) FROM outbox_message") == 0
        set_claim(db, b, "sent")
        assert (await c.post(URL, cookies=cookies(c, owner))).json()["queued"] is True  # no token was spent


async def test_a_non_owner_including_an_admin_gets_the_unknown_reference_404(world):
    db, _, _ = world
    admin = insert_user(db, role="admin")
    async with api(db, clock_at()) as c:
        r = await c.post(URL, cookies=cookies(c, admin, role="admin"))
        unknown = await c.post("/api/bookings/by-reference/FR-CDEF-HJKJ/resend-receipt", cookies=cookies(c, admin, role="admin"))
    assert r.status_code == unknown.status_code == 404
    assert without_request_id(r.json()) == without_request_id(unknown.json())

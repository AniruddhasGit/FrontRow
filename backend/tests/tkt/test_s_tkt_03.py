"""S-TKT-03 (P-TKT-09, EP-TKT-01): one booking read by its reference, on ownership alone - no admin override, and the
ownership rule lives in the router's one dependency."""

from __future__ import annotations

import pytest

from app.api.receipts import owned_reference
from tests.brw.kit import without_request_id
from tests.dbkit import insert_user
from tests.pay.kit import api, clock_at, cookies, flush
from tests.tkt.kit import booking, owner_sql, truncate

pytestmark = pytest.mark.anyio
URL = "/api/bookings/by-reference/FR-ACDE-FHJD"


@pytest.fixture
def world(migrated_db):
    truncate(migrated_db)
    flush()
    b = booking(migrated_db)
    owner = owner_sql(migrated_db, "SELECT user_id FROM booking WHERE id = %s", (b,))[0][0]
    admin = insert_user(migrated_db, role="admin")
    return migrated_db, owner, admin


async def test_the_owner_reads_exactly_the_eight_keys_with_the_cinemas_offset_and_ordered_seats(world):
    db, owner, _ = world
    async with api(db, clock_at()) as c:
        r = await c.get(URL, cookies=cookies(c, owner))
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"reference", "film_title", "hall_name", "starts_at", "seats", "total_paise", "paid_at", "receipt_email_address"}
        assert body["starts_at"] == "2026-08-21T19:15:00+05:30"
        assert [k for k in body if "local" in k] == []
        assert body["seats"] == ["F7", "F8", "F9"]
        assert body["total_paise"] == 84372
        for banned in ("status", "cancelled_at", "receipt_status", "dispatch_seq"):
            assert banned not in body
        # The stored total, never recomputed: moving the base price moves nothing.
        owner_sql(db, "UPDATE showtime SET base_price_paise = 99999")
        assert (await c.get(URL, cookies=cookies(c, owner))).json()["total_paise"] == 84372


async def test_an_admin_who_does_not_own_it_gets_the_unknown_reference_404(world):
    db, _, admin = world
    async with api(db, clock_at()) as c:
        mine = await c.get(URL, cookies=cookies(c, admin, role="admin"))
        unknown = await c.get("/api/bookings/by-reference/FR-CDEF-HJKJ", cookies=cookies(c, admin, role="admin"))
    assert mine.status_code == unknown.status_code == 404
    assert without_request_id(mine.json()) == without_request_id(unknown.json())


async def test_the_ownership_rule_is_the_one_router_dependency(world):
    db, _, admin = world
    async with api(db, clock_at()) as c:
        c.application.dependency_overrides[owned_reference] = lambda: None  # a pass-through
        r = await c.get(URL, cookies=cookies(c, admin, role="admin"))
    assert r.status_code == 200 and r.json()["reference"] == "FR-ACDE-FHJD"

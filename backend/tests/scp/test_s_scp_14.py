"""S-SCP-14 (P-SCP-11): booking status and its cancellation timestamp are exposed by no endpoint and settable by none.

The teardown census (no cancellation instant, no status but 'confirmed') runs in the shared migrated_db fixture of
backend/tests/conftest.py, through tests/dbkit.py drop_database, for every module; the last test here proves the check
fails on a violating row. The confirmation page's two lines are asserted in
frontend/src/features/ticket/ticket.test.mjs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.pay.kit import F7, J3, api, clock_at, confirm, cookies, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
CONTRACT = Path("/docs") / "03 PRD" / "api" / "contract.json"
STAMP = "cancelled" + "_at"  # assembled, so no source line outside the models names the column (S-PAY-11)


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


def _booking_level(body: dict) -> set[str]:
    return set(body)


async def test_no_live_response_and_no_published_schema_carries_status_or_the_timestamp(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        made = await confirm(c, u, h["hold_token"])
        ref = made.json()["booking_reference"]
        listing = (await c.get("/api/me/bookings", cookies=cookies(c, u))).json()
        one = (await c.get(f"/api/me/bookings/{ref}", cookies=cookies(c, u))).json()
    for row in listing["upcoming"] + listing["past"] + [one, made.json()]:
        assert not {"status", STAMP} & _booking_level(row)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for ep_id in ("EP-ACC-07", "EP-ACC-08", "EP-TKT-01", "EP-PAY-01"):
        ep = next(e for e in contract["endpoints"] if e["id"] == ep_id)
        keys = {k.split(".")[-1] for resp in ep["responses"].values() for k in (resp.get("body") or {})}
        assert not {"status", STAMP} & keys, ep_id


async def test_the_by_reference_read_carries_neither(world):
    """GET /api/bookings/by-reference/{reference} (EP-TKT-01) is lane E4's, Phase 5 (S-TKT-03)."""
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        ref = (await confirm(c, u, h["hold_token"])).json()["booking_reference"]
        r = await c.get(f"/api/bookings/by-reference/{ref}", cookies=cookies(c, u))
    assert r.status_code == 200, r.text
    assert not {"status", STAMP} & set(r.json())


async def test_neither_can_be_set_and_status_is_written_once(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        for extra in ({"status": "cancelled"}, {STAMP: "2026-08-14T14:00:00Z"}):
            r = await confirm(c, u, h["hold_token"], body={"hold_token": h["hold_token"], "showtime_id": 7, **extra})
            assert r.status_code == 400 and r.json()["error"]["code"] == "REQUEST_INVALID"
        assert (await confirm(c, u, h["hold_token"])).status_code == 201
        h2 = await hold(c, u, [J3])
        assert (await confirm(c, u, h2["hold_token"], key="another")).status_code == 201
    assert count(db, f"SELECT count(*) FROM booking WHERE {STAMP} IS NOT NULL") == 0
    assert owner_sql(db, "SELECT DISTINCT status FROM booking") == [("confirmed",)]


async def test_the_shared_teardown_check_fails_on_a_violating_booking():
    """Red-proof of the conftest fixture's teardown: a database holding a cancelled or non-confirmed booking fails it."""
    from tests.dbkit import assert_bookings_never_cancelled, create_database, drop_database
    from tests.pay.kit import book

    db = create_database(migrate=True)
    try:
        w = world7(db)
        b, _ = book(db, user(db), 7, [F7])
        assert_bookings_never_cancelled(db)  # a confirmed, uncancelled booking passes
        owner_sql(db, f"UPDATE booking SET {STAMP} = '2026-08-14T14:00:00Z' WHERE id = %s", (b,))
        with pytest.raises(AssertionError, match="S-SCP-14"):
            assert_bookings_never_cancelled(db)
        owner_sql(db, f"UPDATE booking SET {STAMP} = NULL, status = 'withdrawn' WHERE id = %s", (b,))
        with pytest.raises(AssertionError, match="S-SCP-14"):
            assert_bookings_never_cancelled(db)
        owner_sql(db, "UPDATE booking SET status = 'confirmed' WHERE id = %s", (b,))
        assert w["movie"]
    finally:
        drop_database(db)

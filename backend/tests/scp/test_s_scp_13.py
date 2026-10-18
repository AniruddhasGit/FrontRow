"""S-SCP-13 (P-SCP-02/03/16): the charged total is the sum of the seat prices and carries no other line."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.pay.kit import C1, C2, add_seats, api, clock_at, confirm, cookies, count, hold, make_category, owner_sql, user, world7

pytestmark = pytest.mark.anyio
EXTRA = re.compile(r"fee|booking_fee|convenience|tax|gst|vat|discount|promo|coupon|concession|loyalty|\bpoints\b|food|beverage|order_line",
                   re.IGNORECASE)
CONTRACT = Path("/docs") / "03 PRD" / "api" / "contract.json"


@pytest.fixture
def world(migrated_db):
    w = world7(migrated_db, base=25000)
    plus = make_category(migrated_db, 2000, "Plus")
    add_seats(migrated_db, w["screen"], plus, [(450, "D", 1)], [7])
    return w


def _keys(value) -> list[str]:
    if isinstance(value, dict):
        return [k for k in value] + [k2 for v in value.values() for k2 in _keys(v)]
    if isinstance(value, list):
        return [k for v in value for k in _keys(v)]
    return []


async def test_the_total_is_the_sum_of_three_rounded_seat_prices_and_no_extra_line(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1, C2, 450])
        assert [s["price_paise"] for s in h["seats"]] == [25000, 25000, 30000]
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 201, r.text
        b = r.json()["booking_id"]
        mine = await c.get(f"/api/me/bookings/{r.json()['booking_reference']}", cookies=cookies(c, u))
        listing = await c.get("/api/me/bookings", cookies=cookies(c, u))
    assert owner_sql(db, "SELECT total_paise FROM booking WHERE id = %s", (b,))[0][0] == 80000 == 25000 + 25000 + 30000
    assert count(db, "SELECT sum(price_paise) FROM booking_seat WHERE booking_id = %s", (b,)) == 80000
    for body in (r.json(), mine.json(), listing.json()):
        assert [k for k in _keys(body) if EXTRA.search(k)] == []
    assert [k for k in mine.json() if k.endswith("_paise")] == ["total_paise"]


def test_no_published_response_schema_carries_an_extra_money_line():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    hits = [f"{e['id']}:{k}" for e in contract["endpoints"] for resp in e.get("responses", {}).values()
            for k in (resp.get("body") or {}) if EXTRA.search(k)]
    assert hits == []


async def test_the_by_reference_read_carries_one_money_key(world):
    """GET /api/bookings/by-reference/{reference} (EP-TKT-01) is lane E4's, Phase 5 (S-TKT-03)."""
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1])
        ref = (await confirm(c, u, h["hold_token"])).json()["booking_reference"]
        r = await c.get(f"/api/bookings/by-reference/{ref}", cookies=cookies(c, u))
    assert r.status_code == 200, r.text
    assert [k for k in r.json() if k.endswith("_paise")] == ["total_paise"]


@pytest.mark.parametrize("field", ["promo_code", "discount_code"])
async def test_a_promotion_field_is_refused(world, field):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1])
        r = await confirm(c, u, h["hold_token"], body={"hold_token": h["hold_token"], "showtime_id": 7, field: "X"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "REQUEST_INVALID"

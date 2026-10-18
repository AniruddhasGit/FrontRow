"""S-PAY-03 (P-PAY-05): the price is fixed at hold acquisition and snapshotted onto every booked seat."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.pay.kit import F7, F8, api, clock_at, confirm, cookies, count, hold, owner_sql, r_call, user, world7

pytestmark = pytest.mark.anyio
APP = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_an_admin_price_change_during_the_hold_changes_nothing_already_held(world):
    db = world["db"]
    first, second = user(db), user(db)
    async with api(db, clock_at("2026-08-14T14:00:00+00:00")) as c:
        h = await hold(c, first, [F7])
        assert h["seats"][0]["price_paise"] == 30938  # 27500 + 3438
        c.clock.set("2026-08-14T14:01:10+00:00")
        admin = user(db, "admin")
        edit = await c.patch("/api/admin/showtimes/7", json={"version": 1, "base_price_paise": 30000}, cookies=cookies(c, admin, "admin"))
        assert edit.status_code == 200, edit.text  # the admin's edit is never blocked by a live hold
        assert owner_sql(db, "SELECT base_price_paise FROM showtime WHERE id=7")[0][0] == 30000
        c.clock.set("2026-08-14T14:01:20+00:00")
        h2 = await hold(c, second, [F8])
        assert h2["seats"][0]["price_paise"] == 33750  # 30000 + 3750
        c.clock.set("2026-08-14T14:02:40+00:00")
        r = await confirm(c, first, h["hold_token"])
        assert r.status_code == 201, r.text
        assert (r.json()["seats"][0]["price_paise"], r.json()["total_paise"]) == (30938, 30938)
        r2 = await confirm(c, second, h2["hold_token"], key="second-customer")
        assert r2.json()["total_paise"] == 33750
        b = r.json()["booking_id"]
        price, base, uplift, category = owner_sql(db, "SELECT price_paise, base_price_paise_applied, uplift_basis_points_applied, "
                                                      "seat_category_id FROM booking_seat WHERE booking_id = %s", (b,))[0]
        assert (price, base, uplift) == (30938, 27500, 1250) and category is not None
        assert owner_sql(db, "SELECT amount_paise FROM payment WHERE id = (SELECT payment_id FROM booking WHERE id = %s)",
                         (r2.json()["booking_id"],))[0][0] == 33750
        # After the booking exists, a category edit leaves what was paid untouched.
        owner_sql(db, "UPDATE seat_category SET uplift_basis_points = 2000 WHERE id = %s", (world["premium"],))
        mine = await c.get(f"/api/me/bookings/{r.json()['booking_reference']}", cookies=cookies(c, first))
        assert mine.status_code == 200, mine.text
        assert (mine.json()["seats"][0]["price_paise"], mine.json()["total_paise"]) == (30938, 30938)


def test_the_confirm_path_calls_no_pricing_function():
    assert "seat_price_paise" not in (APP / "api" / "bookings.py").read_text(encoding="utf-8")


async def test_a_hold_with_no_price_snapshot_is_500_and_rolls_back_and_logs_no_money(world, log_capture):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        record = f"hold:{h['hold_token']}"
        entry = json.loads(r_call("HGET", record, f"seat:{F7}"))
        del entry["price_paise"]
        r_call("HSET", record, f"seat:{F7}", json.dumps(entry))
        r = await confirm(c, u, h["hold_token"])
    assert r.status_code == 500
    err = r.json()["error"]
    assert set(r.json()) == {"error"} and set(err) == {"code", "message", "details", "request_id"} and err["code"] == "INTERNAL_ERROR"
    assert err["message"] == f"Something went wrong and your booking was not completed. No payment was taken. If you need help, quote {err['request_id']}."
    assert count(db, "SELECT count(*) FROM booking") == 0 and count(db, "SELECT count(*) FROM payment") == 0
    lines = [ln for ln in log_capture.lines() if ln.get("request_id") == err["request_id"]]
    assert lines
    for ln in lines:
        assert not [k for k in ln if k.endswith("_paise")]
        assert 30938 not in ln.values() and 33750 not in ln.values()

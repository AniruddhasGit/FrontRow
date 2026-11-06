"""S-ADM-15 (P-ADM-12, FR-ADR-039): the price charged is the one current when the hold was granted - the HOLD half.

HERE: the hold value's five fields, the admin edit never refused because a hold exists, the T0+95s confirm writing the
held prices into booking_seat (EP-PAY-01), the T0+120s hold on two other seats quoted at the new base, the hold key's
PTTL against real Redis, no cleanup job, and an admin PATCH waiting on the open confirm's showtime row lock (pg_locks)
and then answering 200. NOT here: EXISTS at T0+179s / T0+181s against an injected-clock Redis test double - the
harness supplies no such double (real Redis expires on its own wall clock), so that clause stays unasserted.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, confirm, owner_sql, r_call, r_pttl, session, user, world77
from tests.xct._support import rg

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"


@pytest.fixture
def world(migrated_db):
    w = world77(migrated_db, retire_412=False)
    owner_sql(w["db"], "UPDATE seat SET seat_category_id = %s WHERE id = 413", (w["standard"],))  # C12 Premium, C13 Standard
    return w


async def test_the_hold_snapshots_the_price_and_the_admin_edit_is_never_refused(world):
    clock = SetClock()
    clock.set(T0)
    customer, admin, later = user(world["db"]), user(world["db"], "admin"), user(world["db"])
    async with api(world["db"], clock) as c:
        mine = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [412, 413]}, cookies=mine)).json()
        record = r_call("HGETALL", f"hold:{hold['hold_token']}")
        pttl = r_pttl("lock:seat:77:412")
        stored = {k: json.loads(v)["price_paise"] for k, v in record.items() if k.startswith("seat:")}
        assert stored == {"seat:412": 28125, "seat:413": 25000}  # (25000*11250+5000)//10000 and (25000*10000+5000)//10000
        assert record["expires_at"] == "2026-08-14T14:05:37.412Z"
        assert 179000 <= pttl <= 180000
        clock.advance(40)
        version = owner_sql(world["db"], "SELECT version FROM showtime WHERE id = 77")[0][0]
        patch = await c.patch("/api/admin/showtimes/77", json={"version": version, "base_price_paise": 30000},
                              cookies=session(c, admin, "admin"))
        assert patch.status_code == 200, patch.text
        assert owner_sql(world["db"], "SELECT version FROM showtime WHERE id = 77")[0][0] == version + 1
        audits = owner_sql(world["db"], "SELECT before, after FROM audit_log WHERE action = 'showtime.base_price_changed' "
                                        "AND entity_id = 77")
        assert audits == [({"base_price_paise": 25000}, {"base_price_paise": 30000})]
        still = (await c.get(f"/api/holds/{hold['hold_token']}", cookies=mine)).json()
        assert [s["price_paise"] for s in still["seats"]] == [28125, 25000]
        clock.advance(55)  # T0 + 95 s: the confirm reads the held prices, never the showtime row
        done = await confirm(c, customer, hold["hold_token"])
        assert done.status_code == 201, done.text
        booking = done.json()["booking_id"]
        rows = owner_sql(world["db"], "SELECT seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied "
                                      "FROM booking_seat WHERE booking_id = %s ORDER BY seat_id", (booking,))
        assert rows == [(412, 28125, 25000, 1250), (413, 25000, 25000, 0)]
        assert [r[1] for r in rows] != [33750, 30000]
        assert owner_sql(world["db"], "SELECT total_paise FROM booking WHERE id = %s", (booking,)) == [(53125,)]
        clock.advance(25)  # T0 + 120 s: a Premium (411) and a Standard (401) seat other than the two just sold
        quoted = (await c.post(URL, json={"seat_ids": [411, 401]}, cookies=session(c, later))).json()
    assert {s["seat_id"]: s["price_paise"] for s in quoted["seats"]} == {411: 33750, 401: 30000}


async def test_an_admin_patch_waits_on_the_open_confirm_and_then_answers_200(world):
    clock = SetClock()
    clock.set(T0)
    customer, admin = user(world["db"]), user(world["db"], "admin")
    async with api(world["db"], clock) as c:
        hold = (await c.post(URL, json={"seat_ids": [412, 413]}, cookies=session(c, customer))).json()
        gate, entered = c.application.state.payment_sleep.hold()  # the confirm stops inside its capture, lock held
        confirming = asyncio.create_task(confirm(c, customer, hold["hold_token"]))
        await asyncio.wait_for(entered.wait(), 10)
        version = owner_sql(world["db"], "SELECT version FROM showtime WHERE id = 77")[0][0]
        patching = asyncio.create_task(c.patch("/api/admin/showtimes/77", json={"version": version, "base_price_paise": 30000},
                                               cookies=session(c, admin, "admin")))
        waiting = []
        for _ in range(200):
            waiting = owner_sql(world["db"], "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE NOT "
                                             "l.granted AND a.usename = 'frontrow_app' AND a.datname = current_database()")
            if waiting:
                break
            await asyncio.sleep(0.05)
        assert waiting, "the PATCH never waited on a lock"
        assert not patching.done()
        assert owner_sql(world["db"], "SELECT count(*) FROM pg_locks WHERE granted = false AND pid = %s", (waiting[0][0],)) == [(1,)]
        gate.set()  # the confirm commits
        done = await asyncio.wait_for(confirming, 10)
        patched = await asyncio.wait_for(patching, 10)
    assert done.status_code == 201, done.text
    assert patched.status_code == 200, patched.text
    assert owner_sql(world["db"], "SELECT price_paise FROM booking_seat WHERE booking_id = %s ORDER BY seat_id",
                     (done.json()["booking_id"],)) == [(28125,), (25000,)]


def test_no_cleanup_job_exists_and_this_module_reads_no_wall_clock():
    assert rg(r"DEL hold|expire_holds|sweep_holds", "backend/app") == []
    assert rg(r"datetime[.]now[(][)]|time[.]time[(][)]", "backend/tests/adm/test_s_adm_15.py") == []

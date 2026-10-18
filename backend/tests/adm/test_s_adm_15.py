"""S-ADM-15 (P-ADM-12, FR-ADR-039): the price charged is the one current when the hold was granted - the HOLD half.

HERE: the hold value's five fields, the admin edit never refused because a hold exists, the next hold quoted at the
new base, the hold key's PTTL against real Redis, and no cleanup job. NOT here: the confirm at T0+95s and its
booking_seat rows, the PATCH waiting on the confirm's showtime row lock (EP-PAY-01, lane PAY, is not mounted), and
EXISTS at T0+179s / T0+181s against an injected-clock Redis test double - the harness supplies no such double.
"""

from __future__ import annotations

import json

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, owner_sql, r_call, r_pttl, session, user, world77
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
        await c.delete(f"/api/holds/{hold['hold_token']}", cookies=mine)
        clock.advance(80)  # T0 + 120 s
        quoted = (await c.post(URL, json={"seat_ids": [412, 413]}, cookies=session(c, later))).json()
    assert [s["price_paise"] for s in quoted["seats"]] == [33750, 30000]


def test_no_cleanup_job_exists_and_this_module_reads_no_wall_clock():
    assert rg(r"DEL hold|expire_holds|sweep_holds", "backend/app") == []
    assert rg(r"datetime[.]now[(][)]|time[.]time[(][)]", "backend/tests/adm/test_s_adm_15.py") == []

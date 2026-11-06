"""S-SEA-09 (P-HLD-04): at most MAX_SEATS_PER_BOOKING seats held at once, per customer, per showtime.

The BOUGHT-ten-then-ten-more case drives the real confirm (EP-PAY-01). Not here: the client's `Up to 6 seats.` at
MAX_SEATS_PER_BOOKING=6 - the cap reaches the client through no endpoint today.
"""

from __future__ import annotations

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_call, r_keys, r_pttl, session, user, world77
from tests.xct._support import rg

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
ELEVEN = [401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411]  # 412 is out of service in this world


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


def _err(r) -> tuple:
    return r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]


async def test_eleven_at_once_is_refused_before_any_lock(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        before = r_keys("lock:seat:77:*")
        r = await c.post(URL, json={"seat_ids": ELEVEN}, cookies=session(c, customer))
        assert r_keys("lock:seat:77:*") == before
    assert _err(r) == (422, "SEAT_LIMIT_EXCEEDED", "You can hold up to 10 seats for one showtime. You chose 11.")


async def test_holding_six_then_five_more_is_refused_and_four_more_is_ten(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        six = (await c.post(URL, json={"seat_ids": [401, 402, 403, 404, 405, 406]}, cookies=cookies)).json()
        pttl = {k: r_pttl(k) for k in r_keys("lock:seat:77:*")}
        c.redis_log.reset()
        five = await c.post(URL, json={"seat_ids": [407, 408, 409, 410, 411]}, cookies=cookies)
        cap_check = list(c.redis_log.commands)
        assert all(0 < r_pttl(k) <= v for k, v in pttl.items()) and len(pttl) == 6
        assert sorted(r_keys("lock:seat:77:*")) == sorted(pttl)
        four = await c.post(URL, json={"seat_ids": [407, 408, 409, 410]}, cookies=cookies)
    assert _err(five) == (422, "SEAT_LIMIT_EXCEEDED",
                          "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.")
    assert not [cmd for cmd in cap_check if cmd[0].upper() in ("SCAN", "KEYS")]
    assert ("SMEMBERS", f"holds:user:{customer}:showtime:77") in cap_check
    assert four.status_code == 201 and len(four.json()["seats"]) == 10
    assert four.json()["expires_at"] == six["expires_at"]


async def test_the_cap_is_per_showtime(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        ten = await c.post(URL, json={"seat_ids": ELEVEN[:10]}, cookies=cookies)
        other = await c.post("/api/showtimes/88/holds", json={"seat_ids": [401, 402, 403, 404]}, cookies=cookies)
        assert r_call("SCARD", f"holds:user:{customer}:showtime:77") == 1
    assert ten.status_code == 201 and other.status_code == 201 and len(other.json()["seats"]) == 4


async def test_the_server_strings_render_the_configured_cap(world):
    customer = user(world["db"])
    async with api(world["db"], _clock(), MAX_SEATS_PER_BOOKING="6") as c:
        cookies = session(c, customer)
        seven = await c.post(URL, json={"seat_ids": ELEVEN[:7]}, cookies=cookies)
        await c.post(URL, json={"seat_ids": ELEVEN[:4]}, cookies=cookies)
        three = await c.post(URL, json={"seat_ids": ELEVEN[4:7]}, cookies=cookies)
    assert _err(seven) == (422, "SEAT_LIMIT_EXCEEDED", "You can hold up to 6 seats for one showtime. You chose 7.")
    assert _err(three) == (422, "SEAT_LIMIT_EXCEEDED",
                           "You can hold up to 6 seats for one showtime. You are holding 4 and chose 3 more.")


async def test_bought_seats_count_nothing_against_the_cap(migrated_db):
    """Ten bought on 77, then ten more held at once on 77: 201, because the commit removed the spent token."""
    from tests.sea.kit import confirm, owner_sql

    world = world77(migrated_db, retire_412=False)  # 401..418 and 420 in 77's set: 19 seats
    for n in (21, 22):  # one more in-service seat in 77's set, so twenty distinct seats exist
        owner_sql(migrated_db, "INSERT INTO seat (id, screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
                               "OVERRIDING SYSTEM VALUE VALUES (%s, 3, 'C', %s, 3, %s, %s)", (400 + n, n, n, world["standard"]))
        owner_sql(migrated_db, "INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (77, %s)", (400 + n,))
    first, second = list(range(401, 411)), [411, 412, 413, 414, 415, 416, 417, 418, 420, 421]
    customer = user(migrated_db)
    async with api(migrated_db, _clock()) as c:
        cookies = session(c, customer)
        held = await c.post(URL, json={"seat_ids": first}, cookies=cookies)
        assert held.status_code == 201, held.text
        bought = await confirm(c, customer, held.json()["hold_token"])
        assert bought.status_code == 201, bought.text
        after_purchase = r_call("SCARD", f"holds:user:{customer}:showtime:77")
        again = await c.post(URL, json={"seat_ids": second}, cookies=cookies)
        after_hold = r_call("SCARD", f"holds:user:{customer}:showtime:77")
    assert after_purchase == 0
    assert again.status_code == 201, again.text
    assert len(again.json()["seats"]) == 10 and after_hold == 1


def test_no_literal_ten_ships_in_a_cap_string():
    assert rg("up to 10 seats", "backend/app", "backend/migrations", "frontend/src", ignore_case=True, fixed=True) == []

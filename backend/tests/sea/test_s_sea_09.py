"""S-SEA-09 (P-HLD-04): at most MAX_SEATS_PER_BOOKING seats held at once, per customer, per showtime.

The client's `Up to 6 seats.` is rendered from the seat map's max_seats_per_booking (CR-002 C-1): the server half is
asserted here, the rendered note in frontend/src/features/seatmap/render.test.mjs.
"""

from __future__ import annotations

import pytest

from tests.dbkit import owner_sql
from tests.sea.kit import (SHOWTIME, T0, SetClock, api, confirm, flush, r_call, r_keys, r_pttl, seat,
                            session, user, world77)
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


async def test_bought_ten_then_ten_more_is_a_201(world):
    """Bought seats count against nothing: the confirm removes the spent token from the cap set (OPEN-BULKBUY-01)."""
    for n in range(1, 11):  # row D: ten more in-service seats in showtime 77's set, so twenty are free
        seat(world["db"], world["screen"], 430 + n, "D", n, 4, n, world["standard"])
    owner_sql(world["db"], "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT 77, id FROM seat WHERE id > 430")
    customer = user(world["db"])
    first, second = ELEVEN[:10], [431 + i for i in range(10)]
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        held = (await c.post(URL, json={"seat_ids": first}, cookies=cookies)).json()
        bought = await confirm(c, customer, held["hold_token"])
        after_purchase = r_call("SCARD", f"holds:user:{customer}:showtime:77")
        again = await c.post(URL, json={"seat_ids": second}, cookies=cookies)
        after_hold = r_call("SCARD", f"holds:user:{customer}:showtime:77")
    assert bought.status_code == 201, bought.text
    assert (after_purchase, after_hold) == (0, 1)
    assert again.status_code == 201 and len(again.json()["seats"]) == 10


async def test_the_seat_map_publishes_the_configured_cap(world):
    """CR-002 C-1: EP-BRW-06 carries max_seats_per_booking, so the client's note needs no literal of its own."""
    async with api(world["db"], _clock(), MAX_SEATS_PER_BOOKING="6") as c:
        six = (await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")).json()
    flush()  # the seat map is cached in Redis; the second app builds its own
    async with api(world["db"], _clock()) as c:
        ten = (await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")).json()
    assert (six["max_seats_per_booking"], ten["max_seats_per_booking"]) == (6, 10)
    assert type(six["max_seats_per_booking"]) is int


def test_no_literal_ten_ships_in_a_cap_string():
    assert rg("up to 10 seats", "backend/app", "backend/migrations", "frontend/src", ignore_case=True, fixed=True) == []

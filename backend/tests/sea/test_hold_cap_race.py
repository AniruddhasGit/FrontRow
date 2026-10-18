"""The cap holds under concurrency: two simultaneous first holds from one customer cannot together pass it."""

from __future__ import annotations

import asyncio

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, session, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"


async def test_two_simultaneous_first_holds_cannot_both_fill_the_cap(migrated_db):
    world = world77(migrated_db)
    customer = user(world["db"])
    clock = SetClock()
    clock.set(T0)
    async with api(world["db"], clock, MAX_SEATS_PER_BOOKING="3") as c:
        cookies = session(c, customer)
        a, b = await asyncio.gather(c.post(URL, json={"seat_ids": [401, 402, 403]}, cookies=cookies),
                                    c.post(URL, json={"seat_ids": [404, 405, 406]}, cookies=cookies))
        assert sorted([a.status_code, b.status_code]) == [201, 422], (a.text, b.text)
        loser = a if a.status_code == 422 else b
        assert loser.json()["error"]["code"] == "SEAT_LIMIT_EXCEEDED"

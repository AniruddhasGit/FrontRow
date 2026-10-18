"""S-SEA-06 (P-SEA-01, P-HLD-01, EP-HLD-01): every seat id is validated server-side before any lock is touched."""

from __future__ import annotations

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, owner_sql, r_call, r_keys, session, showtime, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


CASES = [
    (URL, [402, 402], 422, "VALIDATION_FAILED", "Seat C2 was listed twice. Each seat can only be chosen once. No seats were held."),
    (URL, [407, 407], 422, "VALIDATION_FAILED", "Seat C7 was listed twice. Each seat can only be chosen once. No seats were held."),
    (URL, [419], 422, "VALIDATION_FAILED", "Seat C19 is not part of this hall. No seats were held."),
    (URL, [412], 422, "VALIDATION_FAILED", "Seat C12 is out of service. No seats were held."),
    (URL, [], 422, "VALIDATION_FAILED", "Choose at least one seat."),
    ("/api/showtimes/999999/holds", [402], 404, "NOT_FOUND", "That showtime could not be found."),
]


@pytest.mark.parametrize("url,seat_ids,status,code,message", CASES)
async def test_each_refusal_holds_nothing_and_sends_no_set(world, url, seat_ids, status, code, message):
    customer = user(world["db"])
    r_call("SET", "lock:seat:77:405", "someone-else", "PX", "300000")  # a pre-existing key the refusal must not move
    async with api(world["db"], _clock()) as c:
        before = r_keys("lock:seat:77:*")
        c.redis_log.reset()
        r = await c.post(url, json={"seat_ids": seat_ids}, cookies=session(c, customer))
        sent = list(c.redis_log.commands)
        assert r_keys("lock:seat:77:*") == before
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (status, code, message)
    assert not [s for s in sent if s[0].upper() == "SET"]


async def test_membership_is_the_materialised_set_not_the_screen(world):
    """419 was added to screen 3 after showtime 77 existed: refused on 77, holdable on a showtime created after it."""
    later = showtime(world["db"], world["movie"], world["screen"], 99)
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        refused = await c.post(URL, json={"seat_ids": [419]}, cookies=session(c, customer))
        granted = await c.post(f"/api/showtimes/{later}/holds", json={"seat_ids": [419]}, cookies=session(c, customer))
    assert refused.status_code == 422
    assert refused.json()["error"]["message"] == "Seat C19 is not part of this hall. No seats were held."
    assert granted.status_code == 201, granted.text


async def test_membership_and_service_are_independent_checks(world):
    """412 IS in showtime 77's seat set and is out of service: the service sentence, never the membership one."""
    assert owner_sql(world["db"], "SELECT count(*) FROM showtime_seat WHERE showtime_id = 77 AND seat_id = 412")[0][0] == 1
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        r = await c.post(URL, json={"seat_ids": [412]}, cookies=session(c, customer))
    assert r.json()["error"]["message"] == "Seat C12 is out of service. No seats were held."

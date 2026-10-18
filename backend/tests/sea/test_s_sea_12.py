"""S-SEA-12 (P-HLD-07): name the seats that went, by their customer-facing label, and never blame the customer.

The client half - repainting the named seats held_by_other, keeping the rest of fr.selection, branching on
error.code - is unit-tested in frontend/src/features/seatmap/hold.test.mjs. The rendered fill, mark and accessible
name need a browser harness and are not asserted here.
"""

from __future__ import annotations

import re

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, book, r_call, r_pttl, session, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
FIRST_TWO = ("C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected — "
             "change these two and press Hold these seats again.")
FIRST_ONE = "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again."
EXTEND_TWO = ("C12 and C13 were taken by another customer. Your hold is unchanged. Your other choices are still selected — "
              "change these two and try again.")
EXTEND_ONE = "C12 was taken by another customer. Your hold is unchanged. Choose a different seat and try again."
LABEL = re.compile(r"^[A-Z]+[0-9]+$")


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db, retire_412=False)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


def _taken_by_someone_else(*seat_ids: int) -> None:
    for s in seat_ids:
        r_call("SET", f"lock:seat:77:{s}", "another-customers-hold-token", "PX", "300000")


async def test_first_hold_losing_two_and_losing_one(world):
    customer = user(world["db"])
    _taken_by_someone_else(412, 413)
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        two = await c.post(URL, json={"seat_ids": [410, 411, 412, 413, 414]}, cookies=cookies)
        one = await c.post(URL, json={"seat_ids": [411, 412]}, cookies=cookies)
        payload = (await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")).json()
    labels = {s["id"]: f"{s['row']}{s['num']}" for s in payload["seats"]}
    e2, e1 = two.json()["error"], one.json()["error"]
    assert (two.status_code, e2["code"], e2["details"]["unavailable_seats"], e2["message"]) == (409, "SEAT_UNAVAILABLE", ["C12", "C13"], FIRST_TWO)
    assert (one.status_code, e1["code"], e1["details"]["unavailable_seats"], e1["message"]) == (409, "SEAT_UNAVAILABLE", ["C12"], FIRST_ONE)
    for value, seat_id in zip(e2["details"]["unavailable_seats"], (412, 413)):
        assert value == labels[seat_id] and LABEL.match(value) and value != str(seat_id)


async def test_extending_a_live_hold_says_the_hold_is_unchanged_and_moves_nothing(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [410]}, cookies=cookies)).json()
        _taken_by_someone_else(412, 413)
        before = r_pttl("lock:seat:77:410")
        two = await c.post(URL, json={"seat_ids": [412, 413]}, cookies=cookies)
        one = await c.post(URL, json={"seat_ids": [412]}, cookies=cookies)
        after = r_pttl("lock:seat:77:410")
        read = (await c.get(f"/api/holds/{hold['hold_token']}", cookies=cookies)).json()
    assert (two.json()["error"]["message"], two.json()["error"]["details"]["unavailable_seats"]) == (EXTEND_TWO, ["C12", "C13"])
    assert (one.json()["error"]["message"], one.json()["error"]["details"]["unavailable_seats"]) == (EXTEND_ONE, ["C12"])
    assert read["expires_at"] == hold["expires_at"] and [s["seat_id"] for s in read["seats"]] == [410]
    assert before - 1000 <= after <= before


async def test_a_seat_sold_since_the_map_was_drawn_gets_the_one_seat_sentence(world):
    book(world["db"], 77, 412)
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        r = await c.post(URL, json={"seat_ids": [412]}, cookies=session(c, customer))
    assert (r.status_code, r.json()["error"]["details"]["unavailable_seats"], r.json()["error"]["message"]) == (409, ["C12"], FIRST_ONE)


def test_no_sentence_apologises_or_exclaims():
    for sentence in (FIRST_TWO, FIRST_ONE, EXTEND_TWO, EXTEND_ONE):
        assert not re.search(r"sorry|apolog|unfortunat|regret|!", sentence, re.I)

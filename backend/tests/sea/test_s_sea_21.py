"""S-SEA-21 (P-SEA-05): sold wins over any lock when the seat map is assembled - and the rule is written once.

Not here (browser harness): the rendered cell (fill, hatch, no border, accessible name) and the absence of a
banner. The server-side analogue IS here: seat 402's own object is identical with the residual lock and without.
"""

from __future__ import annotations

import pytest

from app.domain.browse import seatmap
from tests.sea.kit import SHOWTIME, T0, SetClock, api, book, r_call, world77

pytestmark = pytest.mark.anyio
MAP = f"/api/showtimes/{SHOWTIME}/seatmap"


@pytest.fixture
def world(migrated_db):
    w = world77(migrated_db)
    book(w["db"], 77, 402)  # a committed booking_seat row for (77, 402)
    return w


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


def _state(body: dict, seat_id: int) -> str:
    return next(s for s in body["seats"] if s["id"] == seat_id)["state"]


async def _four_cases(c):
    """(booked + lock) on 402, lock only on 403, neither on 404, booked only on 402 once its lock is gone."""
    r_call("SET", "lock:seat:77:402", "a-residual-lock", "PX", "300000")
    r_call("SET", "lock:seat:77:403", "a-live-hold", "PX", "300000")
    both = await c.get(MAP)
    r_call("DEL", "lock:seat:77:402")
    booked_only = await c.get(MAP)
    return both, booked_only


async def test_sold_wins_and_only_three_states_exist(world):
    async with api(world["db"], _clock()) as c:
        both, booked_only = await _four_cases(c)
    b1, b2 = both.json(), booked_only.json()
    assert (_state(b1, 402), _state(b1, 403), _state(b1, 404), _state(b2, 402)) == ("sold", "held", "available", "sold")
    assert {s["state"] for s in b1["seats"] + b2["seats"]} <= {"available", "sold", "held"}
    # Seat 402's OWN object, with the residual lock and without it: identical.
    assert next(s for s in b1["seats"] if s["id"] == 402) == next(s for s in b2["seats"] if s["id"] == 402)


async def test_the_precedence_is_implemented_once(world, monkeypatch):
    def raising(booked: bool, held: bool) -> str:
        raise RuntimeError("the one precedence rule was replaced")

    monkeypatch.setattr(seatmap, "seat_state", raising)
    async with api(world["db"], _clock()) as c:
        both, booked_only = await _four_cases(c)
    assert both.status_code == booked_only.status_code == 500  # every case raised; none still answered


async def test_redis_unreachable_is_503_with_the_maps_sentence(world):
    from tests.sea.test_s_sea_15 import unreachable

    async with unreachable(world["db"]) as c:
        r = await c.get(MAP)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
        503, "DEPENDENCY_UNAVAILABLE", "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes.")

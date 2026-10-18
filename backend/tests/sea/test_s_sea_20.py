"""S-SEA-20 (P-SEA-06): the seat lifecycle machine - the parts that need neither the confirm nor a browser.

HERE: the normative block itself (5 states x 29 inputs = 145 rows, every row complete, no SHOWTIME_WITHDRAWN), and
the projections of the three states the hold path alone reaches: available, held_by_me (HOLD_ACQUIRE_OK),
held_by_other (OTHER_ACQUIRES). NOT here: held_by_me_paying and sold reached by CONFIRM_START / CONFIRM_COMMIT and
every row driven by them (EP-PAY-01, lane PAY), and every rendered cell, SIGN_OUT and TAB_CLOSED (browser harness).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, owner_sql, r_call, session, user, world77
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio


def _block() -> dict:
    prd = (REPO / "docs/03 PRD/FrontRow_PRD.md").read_text(encoding="utf-8")
    start = prd.index("#### `P-SEA-06`")
    fenced = re.search(r"```transition\n(.*?)\n```", prd[start:], re.S).group(1)
    return json.loads(fenced)


def test_the_normative_block_is_complete():
    block = _block()
    states, inputs, rows = block["states"], block["inputs"], block["transitions"]
    assert (len(states), len(inputs), len(rows)) == (5, 29, 145)
    assert not [r for r in rows if not all(k in r for k in ("to", "guard", "user_sees"))]
    assert {(r["from"], r["input"]) for r in rows} == {(s, i) for s in states for i in inputs}
    assert "SHOWTIME_WITHDRAWN" not in inputs


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


async def _projection(c, token_of_this_session: str | None) -> tuple:
    value = r_call("GET", "lock:seat:77:402")
    booked = owner_sql(c.db, "SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = 402")[0][0]
    state = next(s for s in (await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")).json()["seats"] if s["id"] == 402)["state"]
    mine = None if value is None else value == token_of_this_session
    return mine, booked, state


async def test_the_three_states_the_hold_path_reaches(world):
    me, someone = user(world["db"]), user(world["db"])
    clock = SetClock()
    clock.set(T0)
    async with api(world["db"], clock) as c:
        c.db = world["db"]
        assert await _projection(c, None) == (None, 0, "available")
        hold = (await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [402]}, cookies=session(c, me))).json()
        assert await _projection(c, hold["hold_token"]) == (True, 0, "held")  # held_by_me, by HOLD_ACQUIRE_OK
        await c.delete(f"/api/holds/{hold['hold_token']}", cookies=session(c, me))
        assert await _projection(c, hold["hold_token"]) == (None, 0, "available")
        await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [402]}, cookies=session(c, someone))
        assert await _projection(c, hold["hold_token"]) == (False, 0, "held")  # held_by_other, by OTHER_ACQUIRES

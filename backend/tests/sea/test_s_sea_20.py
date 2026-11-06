"""S-SEA-20 (P-SEA-06): the seat lifecycle machine, through the observable projection of each state.

HERE: the normative block itself (5 states x 29 inputs = 145 rows, every row complete, no SHOWTIME_WITHDRAWN); the
projections of all five states - available, held_by_me (HOLD_ACQUIRE_OK), held_by_other (OTHER_ACQUIRES),
held_by_me_paying (CONFIRM_START, gated inside the simulated provider) and sold (CONFIRM_COMMIT); the impossible
available x CONFIRM_START taking CONFIRM_HOLD_GONE (409 HOLD_EXPIRED, no payment attempted); SALES_CUTOFF_PASSES
changing no projection. NOT here (the row stays Blocked): driving the other 145-row transitions one by one, including
the payment-failed and instance-killed rows and the rest of the impossible-guard attempts, and every rendered cell,
SIGN_OUT and TAB_CLOSED with their spies, and the held_by_me_paying vs held_by_me DOM comparison (browser harness).
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


async def test_confirm_start_then_commit_reaches_paying_then_sold(world):
    """held_by_me --CONFIRM_START--> held_by_me_paying (this test's confirm is inside the provider and has not
    returned: the projection is held_by_me's) --CONFIRM_COMMIT--> sold."""
    import asyncio

    from tests.sea.kit import confirm

    me = user(world["db"])
    clock = SetClock()
    clock.set(T0)
    async with api(world["db"], clock) as c:
        c.db = world["db"]
        hold = (await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [402]}, cookies=session(c, me))).json()
        gate, entered = c.application.state.payment_sleep.hold()
        paying = asyncio.create_task(confirm(c, me, hold["hold_token"]))
        await asyncio.wait_for(entered.wait(), 10)
        assert not paying.done()
        assert await _projection(c, hold["hold_token"]) == (True, 0, "held")  # held_by_me_paying
        gate.set()
        r = await asyncio.wait_for(paying, 10)
        assert r.status_code == 201, r.text
        mine, booked, state = await _projection(c, hold["hold_token"])
    assert (booked, state) == (1, "sold")  # sold: (any, 1, sold)


async def test_a_confirm_against_an_available_seat_takes_hold_gone_and_attempts_no_payment(world):
    """available x CONFIRM_START is impossible: with no key the confirm takes CONFIRM_HOLD_GONE, 409 HOLD_EXPIRED,
    before any payment is attempted (no payment row, and the simulated provider's delay port never called)."""
    from tests.sea.kit import confirm, payments

    me = user(world["db"])
    clock = SetClock()
    clock.set(T0)
    async with api(world["db"], clock) as c:
        c.db = world["db"]
        hold = (await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [402]}, cookies=session(c, me))).json()
        r_call("DEL", "lock:seat:77:402")
        assert await _projection(c, hold["hold_token"]) == (None, 0, "available")
        before = payments(world["db"])
        r = await confirm(c, me, hold["hold_token"])
        assert await _projection(c, hold["hold_token"]) == (None, 0, "available")
        provider_calls = list(c.application.state.payment_sleep.calls)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "HOLD_EXPIRED")
    assert payments(world["db"]) == before and provider_calls == []


async def test_sales_cutoff_passing_changes_no_projection(world):
    """SALES_CUTOFF_PASSES in available, held_by_me, held_by_other and sold: the triple is identical before and after
    the injected clock crosses 19:45 (held_by_me_paying shares held_by_me's triple)."""
    from tests.sea.kit import book

    me, someone = user(world["db"]), user(world["db"])
    book(world["db"], SHOWTIME, 405)
    clock = SetClock()
    clock.set("2026-08-14T19:40:00+05:30")
    async with api(world["db"], clock) as c:
        mine = (await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [403]}, cookies=session(c, me))).json()
        await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [404]}, cookies=session(c, someone))

        async def triples():
            states = {s["id"]: s["state"] for s in (await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")).json()["seats"]}
            out = []
            for sid in (402, 403, 404, 405):
                booked = owner_sql(world["db"], "SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = %s",
                                   (sid,))[0][0]
                out.append((r_call("GET", f"lock:seat:77:{sid}"), booked, states[sid]))
            return out

        before = await triples()
        clock.set("2026-08-14T19:46:00+05:30")
        after = await triples()
    assert [t[2] for t in before] == ["available", "held", "held", "sold"]
    assert before[1][0] == mine["hold_token"] and before[2][0] not in (None, mine["hold_token"])
    assert after == before

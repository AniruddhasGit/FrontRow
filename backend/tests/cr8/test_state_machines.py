"""CR-008 T14: the state-machine review's server findings (#4 Give up during a confirm, #8 release racing extend)."""

from __future__ import annotations

import asyncio

import pytest

from app.domain import holds
from tests.pay.kit import F7, F8, SHOWTIME, api, clock_at, confirm, cookies, count, hold, r_call, user, world7

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_giving_up_during_the_payment_is_refused_until_it_ends(world):
    """#4: the customer presses Give up (header Back, then Give up) while their payment runs. The release is refused
    with "being processed", so no other customer can take seats this payment is about to book; the booking then
    completes, and Give up works again afterwards (nothing is left held)."""
    db = world["db"]
    me = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, me, [F7, F8])
        token = h["hold_token"]
        seen = {}

        async def give_up_meanwhile(ms):
            r = await c.delete(f"/api/holds/{token}", cookies=cookies(c, me))
            seen["during"] = (r.status_code, r.json()["error"]["code"])

        c.application.state.payment_sleep = give_up_meanwhile
        r = await confirm(c, me, token)
        assert r.status_code == 201, r.text
        assert seen["during"] == (409, "IDEMPOTENCY_IN_FLIGHT")
        assert r_call("EXISTS", holds.confirming_key(token)) == 0  # cleared on the way out
    assert count(db, "SELECT count(*) FROM booking") == 1


async def test_a_failed_payment_clears_the_paying_mark(world):
    db = world["db"]
    me = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, me, [F7])
        r = await confirm(c, me, h["hold_token"], key="FAIL_" + "0" * 30)
        assert r.status_code == 402, r.text
        assert (await c.delete(f"/api/holds/{h['hold_token']}", cookies=cookies(c, me))).status_code == 204


async def test_giving_up_waits_for_the_customers_hold_mutex(world):
    """#8: release and extend for one customer and showtime are serialised by the same mutex as acquire, so an
    extend can never re-create a half record that a release just deleted."""
    db = world["db"]
    me = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, me, [F7])
        key = holds.mutex_key(me, SHOWTIME)
        r_call("SET", key, "someone-else", "PX", "60000")  # another request of this customer is mid-flight
        task = asyncio.create_task(c.delete(f"/api/holds/{h['hold_token']}", cookies=cookies(c, me)))
        await asyncio.sleep(0.4)
        assert not task.done(), "the release did not wait for the mutex"
        r_call("DEL", key)
        r = await asyncio.wait_for(task, 5)
        assert r.status_code == 204, r.text

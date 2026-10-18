"""S-SEA-13 (P-HLD-08, EP-HLD-03, EP-HLD-04): give seats back - one, all, and after the hold has gone - and the
two release-versus-confirm orderings (EP-PAY-01).
"""

from __future__ import annotations

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_call, r_pttl, session, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
RECLINERS = [416, 417, 418]  # 33333 paise each at base 25000


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


async def test_one_seat_back_keeps_the_rest_and_the_expiry(world):
    customer, other = user(world["db"]), user(world["db"])
    async with api(world["db"], _clock()) as c:
        mine = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": RECLINERS}, cookies=mine)).json()
        assert hold["total_paise"] == 99999
        theirs = (await c.post(URL, json={"seat_ids": [401]}, cookies=session(c, other))).json()
        wrong = await c.delete(f"/api/holds/{theirs['hold_token']}/seats/401", cookies=mine)
        assert r_call("GET", "lock:seat:77:401") == theirs["hold_token"]
        before = {s: r_pttl(f"lock:seat:77:{s}") for s in (417, 418)}
        r = await c.delete(f"/api/holds/{hold['hold_token']}/seats/416", cookies=mine)
        assert r_call("EXISTS", "lock:seat:77:416") == 0
        for s, p in before.items():
            assert p - 1000 <= r_pttl(f"lock:seat:77:{s}") <= p
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (403, "HOLD_NOT_OWNED")
    body = r.json()
    assert r.status_code == 200 and [s["seat_id"] for s in body["seats"]] == [417, 418]
    assert body["total_paise"] == 66666 and body["expires_at"] == hold["expires_at"]


async def test_the_last_seat_ends_the_hold_and_frees_the_cap(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [416]}, cookies=cookies)).json()
        r = await c.delete(f"/api/holds/{hold['hold_token']}/seats/416", cookies=cookies)
        assert r_call("EXISTS", f"hold:{hold['hold_token']}") == 0
        assert r_call("SCARD", f"holds:user:{customer}:showtime:77") == 0
        ten = await c.post(URL, json={"seat_ids": [401, 402, 403, 404, 405, 406, 407, 408, 409, 410]}, cookies=cookies)
    assert r.status_code == 200 and r.json()["seats"] == [] and r.json()["total_paise"] == 0
    assert ten.status_code == 201


async def test_the_whole_hold_back_in_order_and_the_cache_last(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [418, 402, 410]}, cookies=cookies)).json()
        token = hold["hold_token"]
        registry = f"instance:{c.application.state.instance_id}:holds"
        r_call("DEL", "lock:seat:77:410")  # expired on its own: its compare-and-delete returns 0 and the loop goes on
        c.redis_log.reset()
        r = await c.delete(f"/api/holds/{token}", cookies=cookies)
        sent = list(c.redis_log.commands)
        assert r_call("EXISTS", "lock:seat:77:402") == 0 and r_call("EXISTS", "lock:seat:77:418") == 0
        assert r_call("SMEMBERS", registry) == set()
        assert r_call("EXISTS", f"hold:{token}") == 0 and r_call("SCARD", f"holds:user:{customer}:showtime:77") == 0
    assert r.status_code == 204 and r.content == b""
    releases = [cmd[3] for cmd in sent if cmd[0] == "EVAL" and cmd[3].startswith("lock:seat:")]
    assert releases == ["lock:seat:77:402", "lock:seat:77:410", "lock:seat:77:418"]
    cache_del = [i for i, cmd in enumerate(sent) if cmd[:2] == ("DEL", "cache:seatmap:77")]
    last_release = max(i for i, cmd in enumerate(sent) if cmd[0] == "EVAL" and cmd[3].startswith("lock:seat:"))
    assert cache_del and min(cache_del) > last_release


async def test_a_seat_outside_the_hold_and_a_hold_already_gone(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        outside = await c.delete(f"/api/holds/{hold['hold_token']}/seats/403", cookies=cookies)
        for key in ("lock:seat:77:402", f"hold:{hold['hold_token']}"):
            r_call("DEL", key)  # what Redis's own expiry leaves behind
        c.redis_log.reset()
        gone = await c.delete(f"/api/holds/{hold['hold_token']}", cookies=cookies)
        sent = list(c.redis_log.commands)
    assert (outside.status_code, outside.json()["error"]["code"], outside.json()["error"]["message"]) == (
        422, "VALIDATION_FAILED", "That seat is not part of your hold.")
    assert (gone.status_code, gone.json()["error"]["code"]) == (409, "HOLD_EXPIRED")
    assert not [cmd for cmd in sent if "cache:seatmap:77" in cmd]


# ---- release versus confirm (EP-PAY-01): no release is ever refused because a confirm is in flight ----------


async def test_a_release_before_the_confirm_revalidates_ends_the_confirm_with_nothing_charged(world):
    from tests.sea.kit import confirm, payments

    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        one = (await c.post(URL, json={"seat_ids": [402, 403]}, cookies=cookies)).json()
        seat_back = await c.delete(f"/api/holds/{one['hold_token']}/seats/402", cookies=cookies)
        partial = await confirm(c, customer, one["hold_token"])  # 403 alone is still held: it books
        two = (await c.post(URL, json={"seat_ids": [404]}, cookies=cookies)).json()
        all_back = await c.delete(f"/api/holds/{two['hold_token']}", cookies=cookies)
        captures_before = list(c.application.state.payment_sleep.calls)
        ended = await confirm(c, customer, two["hold_token"])
        captures_after = list(c.application.state.payment_sleep.calls)
    assert seat_back.status_code == 200 and partial.status_code == 201
    assert [s["seat_id"] for s in partial.json()["seats"]] == [403]
    assert (all_back.status_code, ended.status_code, ended.json()["error"]["code"]) == (204, 409, "HOLD_EXPIRED")
    assert captures_after == captures_before  # zero payment attempts for the ended hold
    assert payments(world["db"]) == 1  # the one booking above; nothing for the ended hold


async def test_a_release_after_the_commit_deletes_nothing_and_is_hold_expired(world):
    from tests.sea.kit import confirm, one

    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        booked = await confirm(c, customer, hold["hold_token"])
        late_seat = await c.delete(f"/api/holds/{hold['hold_token']}/seats/402", cookies=cookies)
        late_all = await c.delete(f"/api/holds/{hold['hold_token']}", cookies=cookies)
    assert booked.status_code == 201
    pairs = {(r.status_code, r.json()["error"]["code"]) for r in (late_seat, late_all)}
    assert pairs == {(409, "HOLD_EXPIRED")}  # the commit removed the record; no confirm-specific code exists
    assert one(world["db"], "SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = 402") == 1

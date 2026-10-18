"""S-SEA-05 (P-HLD-01, EP-HLD-01): a multi-seat hold, all or nothing, acquired in ascending seat-id order."""

from __future__ import annotations

import re

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_call, r_keys, r_pttl, session, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


async def test_three_seats_are_three_single_set_nx_px_commands_in_ascending_order(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        log = c.redis_log
        log.reset()
        c.statements.reset()
        r = await c.post(URL, json={"seat_ids": [418, 402, 410]}, cookies=session(c, customer))
        await _assert_granted(c, r, customer)


async def _assert_granted(c, r, customer):
    """Asserted while the app is still running: its shutdown hook releases this instance's holds (S-SEA-17)."""
    log = c.redis_log
    assert r.status_code == 201, r.text
    body = r.json()
    sets = log.of("SET")
    lock_sets = [s for s in sets if s[1].startswith("lock:seat:")]
    assert [s[1] for s in lock_sets] == ["lock:seat:77:402", "lock:seat:77:410", "lock:seat:77:418"]
    for s in lock_sets:
        assert s[2] == body["hold_token"] and s[3:5] == ("NX", "PX") and s[5] == "180000" and len(s) == 6
    assert "SETNX" not in log.names() and "EXPIRE" not in log.names()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", body["hold_token"])
    assert body["expires_at"] == "2026-08-14T14:05:37.412Z"
    assert [s["seat_id"] for s in body["seats"]] == [402, 410, 418]
    assert [s["price_paise"] for s in body["seats"]] == [25000, 25000, 33333]
    assert body["total_paise"] == sum(s["price_paise"] for s in body["seats"]) == 83333
    # Indexed against the customer and the instance, both with the hold's TTL.
    index = f"holds:user:{customer}:showtime:77"
    assert r_call("SMEMBERS", index) == {body["hold_token"]}
    assert 179 <= r_call("TTL", index) <= 180
    registry = f"instance:{c.application.state.instance_id}:holds"
    assert sorted(r_call("SMEMBERS", registry)) == ["lock:seat:77:402", "lock:seat:77:410", "lock:seat:77:418"]
    assert 179 <= r_call("TTL", registry) <= 180
    # DEL cache:seatmap:77 after the lock writes, never before.
    order = [(c_[0].upper(), c_[1] if len(c_) > 1 else "") for c_ in log.commands]
    del_at = order.index(("DEL", "cache:seatmap:77"))
    last_lock = max(i for i, x in enumerate(order) if x[0] == "SET" and x[1].startswith("lock:seat:"))
    assert del_at > last_lock
    # No PostgreSQL write at all.
    assert not [s for s in c.statements.statements if s.lstrip().upper().startswith(("INSERT", "UPDATE"))]


async def test_a_lost_seat_releases_what_this_request_won_and_never_writes_the_rest(world):
    customer, other = user(world["db"]), user(world["db"])
    r_call("SET", "lock:seat:77:410", "another-customers-token", "PX", "300000")
    async with api(world["db"], _clock()) as c:
        c.redis_log.reset()
        r = await c.post(URL, json={"seat_ids": [418, 402, 410]}, cookies=session(c, customer))
        log = c.redis_log
        assert r_keys("lock:seat:77:*") == ["lock:seat:77:410"]
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "SEAT_UNAVAILABLE" and err["details"]["unavailable_seats"] == ["C10"]
    locks = [s[1] for s in log.of("SET") if s[1].startswith("lock:seat:")]
    assert locks == ["lock:seat:77:402", "lock:seat:77:410"]  # 418 never written
    evals = log.of("EVAL")
    assert [e[3] for e in evals if "DEL" in e[1] and e[3].startswith("lock:seat:")] == ["lock:seat:77:402"]
    assert r_call("EXISTS", "lock:seat:77:402") == 0 and r_call("EXISTS", "lock:seat:77:418") == 0
    del other


async def test_a_nil_on_a_key_this_customer_already_holds_is_not_a_loss_and_extends_nothing(world):
    customer = user(world["db"])
    clock = _clock()
    async with api(world["db"], clock) as c:
        first = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))
        assert first.status_code == 201
        before = r_pttl("lock:seat:77:402")
        clock.advance(30)
        c.redis_log.reset()
        second = await c.post(URL, json={"seat_ids": [402, 403]}, cookies=session(c, customer))
        assert 0 < r_pttl("lock:seat:77:402") <= before  # not raised
        sent = list(c.redis_log.commands)
    assert second.status_code == 201, second.text
    b1, b2 = first.json(), second.json()
    assert b2["hold_token"] == b1["hold_token"] and b2["expires_at"] == b1["expires_at"]
    assert [s["seat_id"] for s in b2["seats"]] == [402, 403]  # every seat under the token, not only the new one
    new_set = [s for s in sent if s[0] == "SET" and s[1] == "lock:seat:77:403"][0]
    assert int(new_set[5]) == 150000  # the milliseconds remaining to expires_at, never a fresh 180000
    assert not [e for e in sent if e[0] == "EVAL" and "lock:seat:77:402" in e]  # never added to the rollback set


async def test_a_seat_with_a_committed_booking_takes_the_rollback_path(world):
    from tests.sea.kit import book

    book(world["db"], 77, 410)
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        r = await c.post(URL, json={"seat_ids": [402, 410]}, cookies=session(c, customer))
    assert r.status_code == 409 and r.json()["error"]["code"] == "SEAT_UNAVAILABLE"
    assert r.json()["error"]["details"]["unavailable_seats"] == ["C10"]
    assert r_keys("lock:seat:77:*") == []

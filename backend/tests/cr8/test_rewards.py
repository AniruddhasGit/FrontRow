"""CR-008 T3 (rewards) and T7 (event notifications) on the real confirm, plus the checkout-total guard.

Figures are the pay lane's world (tests/pay/kit.py): F7/F8/F9 Premium 30938, J3/J4 Recliner 36666, C1-C3 Standard
27500. Rules (app/domain/rewards.py): 10 points per whole dollar paid; 100 points = $1.00; discount capped at 50%.
"""

from __future__ import annotations

import asyncio

import psycopg
import pytest

from app.domain import rewards
from tests.pay.kit import (C1, F7, F8, F9, FIVE, SHOWTIME, api, clock_at, confirm, cookies, count, hold, movie_and_showtime,
                           owner_sql, r_call, user, world7)

pytestmark = pytest.mark.anyio
SECOND = 8  # a second showtime of the same film, for two holds by one customer at once


@pytest.fixture
def world(migrated_db):
    w = world7(migrated_db)
    movie_and_showtime(migrated_db, w, SECOND, "2026-08-14T23:00:00+05:30")
    return w


def balance(db, u: int) -> int:
    return count(db, "SELECT points_balance FROM users WHERE id = %s", (u,))


def give(db, u: int, points: int) -> None:
    owner_sql(db, "UPDATE users SET points_balance = %s WHERE id = %s", (points, u))


def body(h: dict, **extra) -> dict:
    return {"hold_token": h["hold_token"], "showtime_id": h["showtime_id"], **extra}


async def test_a_paid_booking_earns_points_once_and_notifies(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7, F8])  # 61876 cents -> 618 whole dollars -> 6180 points
        first = await confirm(c, u, h["hold_token"])
        assert first.status_code == 201, first.text
        replay = await confirm(c, u, h["hold_token"])  # the same Idempotency-Key: the stored answer, nothing new
        assert replay.status_code == 201 and replay.content == first.content
    assert balance(db, u) == 6180
    assert owner_sql(db, "SELECT kind, points, discount_paise FROM reward_entry WHERE user_id = %s", (u,)) == [("earned", 6180, None)]
    kinds = [k for (k,) in owner_sql(db, "SELECT kind FROM notification WHERE user_id = %s ORDER BY id", (u,))]
    assert kinds == ["booking_confirmed", "points_earned"]


async def test_earn_is_idempotent_on_the_booking_even_when_called_twice(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1])
        assert (await confirm(c, u, h["hold_token"])).status_code == 201
        engine = c.application.state.db_engine
        booking_id = count(db, "SELECT id FROM booking WHERE user_id = %s", (u,))
        async with engine.connect() as conn, conn.begin():
            again = await rewards.earn(conn, user_id=u, booking_id=booking_id, paid_paise=27500, ratio=100, now=c.clock.now())
    assert again == 0
    assert balance(db, u) == 2750
    assert count(db, "SELECT count(*) FROM reward_entry WHERE booking_id = %s", (booking_id,)) == 1


async def test_redeeming_takes_the_server_computed_discount_and_pays_a_smaller_total(world):
    db = world["db"]
    u = user(db)
    give(db, u, 100_000)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)  # 166146; the 50% cap allows 83073 points = $830.73
        q = (await c.get("/api/me/rewards", params={"quote_paise": h["total_paise"]}, cookies=cookies(c, u))).json()["quote"]
        assert q == {"points": 83073, "discount_paise": 83073, "total_paise": 83073}
        r = await confirm(c, u, h["hold_token"], body=body(h, use_points=True, expected_total_paise=q["total_paise"]))
        assert r.status_code == 201, r.text
        assert r.json()["total_paise"] == 83073
    assert count(db, "SELECT amount_paise FROM payment WHERE state = 'captured'") == 83073
    # spent 83073, then earned on what was actually paid: 830 whole dollars -> 8300
    assert balance(db, u) == 100_000 - 83073 + 8300
    assert owner_sql(db, "SELECT kind, points, discount_paise FROM reward_entry WHERE user_id = %s ORDER BY kind", (u,)) == \
        [("earned", 8300, None), ("redeemed", 83073, 83073)]
    assert count(db, "SELECT count(*) FROM notification WHERE user_id = %s AND kind = 'points_redeemed'", (u,)) == 1


async def test_the_cap_floors_so_the_total_never_drops_below_half():
    # Exercises the floor: 30939 * 50% = 15469.5. Floored cap 15469 -> pays 15470; a rounded cap would pay 15469.
    assert rewards.quote(30939, 10**9, 100) == {"points": 15469, "discount_paise": 15469, "total_paise": 15470}
    assert rewards.quote(1000, 250, 100) == {"points": 250, "discount_paise": 250, "total_paise": 750}  # balance-bound
    assert rewards.quote(1000, 0, 100)["points"] == 0
    assert rewards.earned_points(99, 100) == 0 and rewards.earned_points(100, 100) == 10


async def test_over_redeeming_is_refused_by_the_conditional_update_and_by_the_check(world):
    db = world["db"]
    u = user(db)
    give(db, u, 500)
    async with api(db, clock_at()) as c:
        async with c.application.state.db_engine.connect() as conn:
            with pytest.raises(rewards.Overdraw):
                async with conn.begin():
                    await rewards.spend(conn, u, 501)
    assert balance(db, u) == 500
    with pytest.raises(psycopg.errors.CheckViolation):
        owner_sql(db, "UPDATE users SET points_balance = points_balance - 501 WHERE id = %s", (u,))


async def test_two_confirms_at_once_spend_the_balance_once(world):
    db = world["db"]
    u = user(db)
    give(db, u, 1000)
    async with api(db, clock_at()) as c:
        a = await hold(c, u, [C1], SHOWTIME)
        b = await hold(c, u, [C1], SECOND)
        gate, entered = c.sleep.hold()  # the first confirm stops inside its payment, holding the users row lock

        async def go(h, key):
            return await confirm(c, u, h["hold_token"], key=key, showtime_id=h["showtime_id"], body=body(h, use_points=True))

        first = asyncio.create_task(go(a, "k-a"))
        await entered.wait()
        second = asyncio.create_task(go(b, "k-b"))
        await asyncio.sleep(0.3)  # real time, so the second is genuinely waiting on the lock, not yet started
        gate.set()
        ra, rb = await first, await second
    assert ra.status_code == 201 and rb.status_code == 201, (ra.text, rb.text)
    # Serialised on the users row: the first spends the 1000 and earns 2650 on its $265 (26500); only then does the second
    # read the balance - 2650, not 1000 - and spends that (27500 - 2650 = 24850), earning 2480. Never 1000 spent twice.
    assert (ra.json()["total_paise"], rb.json()["total_paise"]) == (26500, 24850)
    assert [p for (p,) in owner_sql(db, "SELECT points FROM reward_entry WHERE user_id = %s AND kind = 'redeemed' ORDER BY id", (u,))] ==         [1000, 2650]
    assert balance(db, u) == 2480


async def test_a_failed_payment_rolls_the_redemption_back(world):
    db = world["db"]
    u = user(db)
    give(db, u, 5000)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        r = await confirm(c, u, h["hold_token"], key="FAIL_one", body=body(h, use_points=True))
        assert r.status_code == 402, r.text
    assert balance(db, u) == 5000
    assert count(db, "SELECT count(*) FROM reward_entry") == 0
    assert count(db, "SELECT count(*) FROM notification") == 0
    assert count(db, "SELECT amount_paise FROM payment WHERE state = 'failed'") == 30938 - 5000


async def test_an_expired_hold_spends_nothing(world):
    db = world["db"]
    u = user(db)
    give(db, u, 5000)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        r_call("DEL", f"lock:seat:{SHOWTIME}:{F7}")  # the hold's lock gone: Redis expired it
        r = await confirm(c, u, h["hold_token"], body=body(h, use_points=True))
        assert r.status_code == 409 and r.json()["error"]["code"] == "HOLD_EXPIRED", r.text
    assert balance(db, u) == 5000 and count(db, "SELECT count(*) FROM reward_entry") == 0


async def test_a_total_the_server_does_not_agree_with_is_refused_and_books_nothing(world):
    """The lead's repro: tab A held F7+F8 and shows 61876; tab B added F9 to the SAME server hold. Pay from tab A must
    not book three seats behind a screen that shows two."""
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        a = await hold(c, u, [F7, F8])
        b = await hold(c, u, [F9])  # the other tab: one hold per customer and showtime, so this extends it
        assert b["hold_token"] == a["hold_token"] and b["total_paise"] == 92814
        r = await confirm(c, u, a["hold_token"], body=body(a, expected_total_paise=a["total_paise"]))
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "TOTAL_CHANGED" and r.json()["error"]["details"] == {"total_paise": 92814}
        ok = await confirm(c, u, a["hold_token"], body=body(a, expected_total_paise=92814))  # after re-reading the hold
        assert ok.status_code == 201, ok.text
    assert count(db, "SELECT count(*) FROM booking") == 1
    assert count(db, "SELECT count(*) FROM booking_seat") == 3


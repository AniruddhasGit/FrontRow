"""S-PAY-02's total clause against the PRODUCT: POST /api/bookings returns, charges and stores the sum of the
already-rounded seat prices, never a total rounded once at the end. Kept out of test_s_pay_02.py, whose criterion
forbids the pricing test module from reading any stored data."""

from __future__ import annotations

import pytest

from tests.pay.kit import FIVE, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio


async def test_the_booking_total_is_166146_never_166144(migrated_db):
    db = world7(migrated_db)["db"]  # base 27500: three Premium (1250 bp) at 30938, two Recliner (3333 bp) at 36666
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        r = await confirm(c, u, h["hold_token"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert sorted(s["price_paise"] for s in body["seats"]) == [30938, 30938, 30938, 36666, 36666]
    assert body["total_paise"] == 166146 and body["total_paise"] != 166144
    assert owner_sql(db, "SELECT total_paise FROM booking") == [(166146,)]
    assert owner_sql(db, "SELECT amount_paise FROM payment") == [(166146,)]
    assert count(db, "SELECT sum(price_paise) FROM booking_seat") == 166146

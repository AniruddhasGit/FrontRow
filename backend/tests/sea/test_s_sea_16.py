"""S-SEA-16 (P-HLD-11, FR-ADR-038/039): each seat's price is fixed when THAT seat enters the hold, and the confirm
charges the stored prices without calling the pricing function.
"""

from __future__ import annotations

import json
import re

import pytest

from app.domain.pricing import seat_price_paise
from tests.sea.kit import SHOWTIME, SetClock, api, confirm, owner_sql, r_call, r_pttl, session, user, world77
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


@pytest.mark.parametrize("base,uplift,expected", [(12345, 5000, 18518), (25000, 3333, 33333), (25000, 1250, 28125)])
def test_the_rounding_rule_is_integer_half_up(base, uplift, expected):
    price = seat_price_paise(base, uplift)
    assert type(price) is int and price == expected


async def test_an_admin_price_change_moves_nothing_already_held(world, monkeypatch):
    clock = SetClock()
    clock.set("2026-08-14T14:02:37.412+00:00")  # 19:32:37.412 IST; the app clock is UTC
    customer, admin, next_customer = user(world["db"]), user(world["db"], "admin"), user(world["db"])
    async with api(world["db"], clock) as c:
        mine = session(c, customer)
        first = (await c.post(URL, json={"seat_ids": [416, 417]}, cookies=mine)).json()
        token = first["hold_token"]
        stored = {k: json.loads(v) for k, v in r_call("HGETALL", f"hold:{token}").items() if k.startswith("seat:")}
        assert [s["price_paise"] for s in stored.values()] == [33333, 33333]
        assert 179000 < r_pttl(f"hold:{token}") <= 180000
        clock.set("2026-08-14T14:03:10+00:00")  # 19:33:10 IST
        version = owner_sql(world["db"], "SELECT version FROM showtime WHERE id = 77")[0][0]
        patch = await c.patch("/api/admin/showtimes/77", json={"version": version, "base_price_paise": 30000},
                              cookies=session(c, admin, "admin"))
        assert patch.status_code == 200, patch.text
        after_change = (await c.get(f"/api/holds/{token}", cookies=mine)).json()
        clock.set("2026-08-14T14:03:45+00:00")  # 19:33:45 IST
        third = (await c.post(URL, json={"seat_ids": [418]}, cookies=mine)).json()
        other = (await c.post(URL, json={"seat_ids": [420]}, cookies=session(c, next_customer))).json()
        # The confirm at 19:34:20 reads the stored prices and calls the pricing function zero times.
        clock.set("2026-08-14T14:04:20+00:00")
        calls = []
        import app.domain.holds as holds_module
        import app.domain.pricing as pricing_module

        def spy(*args):
            calls.append(args)
            return seat_price_paise(*args)

        monkeypatch.setattr(pricing_module, "seat_price_paise", spy)
        monkeypatch.setattr(holds_module, "seat_price_paise", spy)
        booked = await confirm(c, customer, token)
        monkeypatch.undo()
    assert booked.status_code == 201, booked.text
    assert calls == []
    assert owner_sql(world["db"], "SELECT amount_paise FROM payment") == [(106665,)]
    assert owner_sql(world["db"], "SELECT seat_id, price_paise, base_price_paise_applied FROM booking_seat ORDER BY seat_id") == [
        (416, 33333, 25000), (417, 33333, 25000), (418, 39999, 30000)]
    assert [s["price_paise"] for s in after_change["seats"]] == [33333, 33333] and after_change["total_paise"] == 66666
    assert [s["price_paise"] for s in third["seats"]] == [33333, 33333, 39999]
    assert third["total_paise"] == 106665 and third["expires_at"] == "2026-08-14T14:05:37.412Z"
    assert [s["price_paise"] for s in other["seats"]] == [39999]


def test_every_money_column_on_the_path_is_bigint():
    schema = (REPO / "docs/06 DataModel/schema.sql").read_text(encoding="utf-8")

    def declared(table: str, column: str) -> str:
        body = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", schema, re.S).group(1)
        return re.search(rf"^\s+{column}\s+(\w+)", body, re.M).group(1)

    pairs = [("showtime", "base_price_paise"), ("booking_seat", "price_paise"), ("booking_seat", "base_price_paise_applied"),
             ("booking", "total_paise")]
    assert [declared(t, c) for t, c in pairs] == ["bigint"] * 4


def test_a_caller_skipping_the_rounding_gets_a_type_error_and_persists_nothing(world):
    before = owner_sql(world["db"], "SELECT count(*) FROM booking_seat WHERE showtime_id = 77")[0][0]
    with pytest.raises(TypeError):
        seat_price_paise(25000.0, 3333)  # type: ignore[arg-type]
    assert owner_sql(world["db"], "SELECT count(*) FROM booking_seat WHERE showtime_id = 77")[0][0] == before


async def test_redis_unreachable_at_confirm_is_503_and_nothing_is_charged(world):
    """The stored prices live only in Redis: with Redis gone they cannot be read, and nothing is charged."""
    from tests.sea.test_s_sea_15 import unreachable

    customer = user(world["db"])
    async with unreachable(world["db"]) as c:
        r = await c.post("/api/bookings", json={"hold_token": "A" * 43, "showtime_id": 77},
                         headers={"Idempotency-Key": "k-16"}, cookies=session(c, customer))
    assert (r.status_code, r.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert owner_sql(world["db"], "SELECT count(*) FROM payment") == [(0,)]
    assert owner_sql(world["db"], "SELECT count(*) FROM booking_seat WHERE showtime_id = 77") == [(0,)]


async def test_redis_failing_at_the_hold_read_of_a_real_hold_is_503_and_nothing_is_charged(world, monkeypatch):
    """The clause as written: a REAL hold, the limiter answered, and Redis failing at holds.load - the read of the
    stored prices - so the confirm cannot know what to charge. 503, nothing charged, nothing booked."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    from tests.sea.kit import T0

    clock = SetClock()
    clock.set(T0)
    customer = user(world["db"])
    steps: list[str] = []
    async with api(world["db"], clock) as c:
        token = (await c.post(URL, json={"seat_ids": [416, 417]}, cookies=session(c, customer))).json()["hold_token"]

        async def unreachable(*args, **kwargs):
            raise RedisConnectionError("Redis unreachable (test double at the hold read)")

        monkeypatch.setattr(c.application.state.redis, "hgetall", unreachable)
        c.application.state.confirm_observer = steps.append
        r = await confirm(c, customer, token)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert steps == ["idempotency insert", "hold re-validation"]  # past the limiter, failing at the hold read
    assert r_call("EXISTS", f"hold:{token}") == 1  # the hold and its stored prices are still there, just unreadable
    assert owner_sql(world["db"], "SELECT count(*) FROM payment") == [(0,)]
    assert owner_sql(world["db"], "SELECT count(*) FROM booking_seat WHERE showtime_id = 77") == [(0,)]
    assert owner_sql(world["db"], "SELECT count(*) FROM idempotency_record") == [(0,)]

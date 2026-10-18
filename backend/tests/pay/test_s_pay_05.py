"""S-PAY-05 (P-PAY-07, P-PAY-01): the simulated payment is captured through pending, authorized and captured."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db import make_engine
from app.domain import payment as pay
from tests.dbkit import app_settings
from tests.pay.kit import FIVE, KEY, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
APP = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_a_confirm_captures_through_three_states_and_records_the_key(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 201, r.text
        assert c.sleep.calls == [1500]  # the delay port, called exactly once with the configured value
    booking_id = r.json()["booking_id"]
    state, amount, key, pending, authorized, captured = owner_sql(
        db, "SELECT state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at FROM payment "
            "WHERE id = (SELECT payment_id FROM booking WHERE id = %s)", (booking_id,))[0]
    assert (state, amount, key) == ("captured", 3 * 30938 + 2 * 36666, KEY) and amount == 166146
    assert pending is not None and authorized is not None and captured is not None
    assert count(db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name='payment' "
                     "AND column_name='booking_id'") == 0
    assert count(db, "SELECT count(*) FROM payment WHERE idempotency_key = %s", (KEY,)) == 1


async def _engine(db):
    settings = app_settings(db)
    return make_engine(settings)


async def test_capture_from_pending_and_anything_from_failed_is_refused(world):
    db = world["db"]
    now = clock_at().now()
    engine = await _engine(db)
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                p = await pay.start(conn, amount_paise=100, idempotency_key="k-1", now=now)
            with pytest.raises(pay.InvalidPaymentTransition):
                async with conn.begin():
                    await pay.capture(conn, p, now)
            assert owner_sql(db, "SELECT state, captured_at FROM payment WHERE id = %s", (p,))[0] == ("pending", None)
            async with conn.begin():
                await pay.fail(conn, p, now)
            for step in (pay.authorize, pay.capture):
                with pytest.raises(pay.InvalidPaymentTransition):
                    async with conn.begin():
                        await step(conn, p, now)
            assert owner_sql(db, "SELECT state FROM payment WHERE id = %s", (p,))[0][0] == "failed"
    finally:
        await engine.dispose()


async def test_a_rolled_back_attempt_then_a_fresh_key_leaves_one_failed_and_one_captured(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        failed = await confirm(c, u, h["hold_token"], key="FAIL_0001")
        assert failed.status_code == 402, failed.text
        ok = await confirm(c, u, h["hold_token"], key="b6d1c0de-0000-4000-8000-000000000001")
        assert ok.status_code == 201, ok.text
    assert sorted(owner_sql(db, "SELECT state, count(*) FROM payment GROUP BY state")) == [("captured", 1), ("failed", 1)]


def test_this_module_measures_no_real_time_and_the_provider_has_no_http_client():
    source = Path(__file__).read_text(encoding="utf-8")
    banned = "|".join(["time" + r"\.sleep", "asyncio" + r"\.sleep", "perf_" + "counter", "time" + r"\.time", "datetime" + r"\.now"])
    assert not re.search(banned, source)
    for f in (APP / "domain" / "payment").rglob("*.py"):
        assert not re.search(r"httpx|requests\.|aiohttp|urllib", f.read_text(encoding="utf-8")), f

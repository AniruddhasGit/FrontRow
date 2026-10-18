"""S-SEA-11 (P-HLD-06, PROVISIONAL +15): the sales cut-off is checked at the hold, in the cinema's zone.

Not here: the two confirm-after-cut-off 201s (EP-PAY-01, lane PAY), the rendered banners (browser harness; their
choice is unit-tested in frontend/src/features/seatmap/hold.test.mjs), and `boot exits non-zero when
SALES_CUTOFF_MINUTES is absent` - app/core/config.py defaults it to 15 as PRD S7.9 publishes.
"""

from __future__ import annotations

import re
import time

import pytest

from app.core.config import ConfigError, load_settings
from tests.sea.kit import SHOWTIME, SetClock, api, r_keys, session, user, world77
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
CLOSED_745 = "Sales for this showtime closed at 7:45 pm. Choose another showtime."


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


async def _hold_at(world, instant: str, **overrides):
    clock = SetClock()
    clock.set(instant)
    customer = user(world["db"])
    async with api(world["db"], clock, **overrides) as c:
        before = r_keys("lock:seat:77:*")
        r = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))
        after = r_keys("lock:seat:77:*")
    return r, before, after


@pytest.mark.parametrize("instant,accepted", [("2026-08-14T19:44:59+05:30", True), ("2026-08-14T19:45:00+05:30", False),
                                              ("2026-08-14T19:45:01+05:30", False)])
async def test_the_boundary_is_now_at_or_after_sales_close(world, instant, accepted):
    r, before, after = await _hold_at(world, instant)
    if accepted:
        assert r.status_code == 201
    else:
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, "SALES_CLOSED", CLOSED_745)
        assert after == before


@pytest.mark.parametrize("instant,accepted", [("2026-08-14T19:14:59+05:30", True), ("2026-08-14T19:15:00+05:30", False),
                                              ("2026-08-14T19:15:01+05:30", False)])
async def test_minus_fifteen_moves_the_boundary_with_no_code_change(world, instant, accepted):
    r, _, _ = await _hold_at(world, instant, SALES_CUTOFF_MINUTES="-15")
    assert r.status_code == (201 if accepted else 409)
    if not accepted:
        assert r.json()["error"]["message"] == "Sales for this showtime closed at 7:15 pm. Choose another showtime."


async def test_the_container_zone_plays_no_part(world, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    try:
        r, _, _ = await _hold_at(world, "2026-08-14T19:45:00+05:30")
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
    assert r.status_code == 409 and r.json()["error"]["message"] == CLOSED_745


async def test_the_seat_map_after_the_cut_off_is_served_and_closed(world):
    clock = SetClock()
    clock.set("2026-08-14T19:45:00+05:30")
    async with api(world["db"], clock) as c:
        r = await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")
    assert r.status_code == 200 and r.json()["showtime"]["sales_closed"] is True


def test_sales_close_at_is_derived_and_never_a_column():
    schema = (REPO / "docs/06 DataModel/schema.sql").read_text(encoding="utf-8")
    table = re.search(r"CREATE TABLE showtime \((.*?)\n\);", schema, re.S).group(1)
    assert "sales_close_at" not in table


@pytest.mark.parametrize("value,boots", [("fifteen", False), ("1.5", False), ("-15", True)])
def test_the_boot_check(valid_env, value, boots):
    valid_env.setenv("SALES_CUTOFF_MINUTES", value)
    if boots:
        assert load_settings().SALES_CUTOFF_MINUTES == -15
    else:
        with pytest.raises(ConfigError):
            load_settings()

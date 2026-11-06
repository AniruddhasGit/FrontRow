"""S-SEA-11 (P-HLD-06, PROVISIONAL +15): the sales cut-off is checked at the hold, in the cinema's zone.

Here too: the two confirm-after-cut-off 201s (EP-PAY-01; each hold's key EXISTS just before), and the boot by process
exit code - non-integer refused, absent boots with the S7.9 default of +15, -15 boots and exits 0 on SIGTERM. The
rendered banners are unit-tested in frontend/src/features/seatmap/hold.test.mjs and render.test.mjs.
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


def test_absent_means_the_s7_9_default_of_plus_fifteen(valid_env):
    assert load_settings().SALES_CUTOFF_MINUTES == 15


@pytest.mark.parametrize("value,exits_zero", [("fifteen", False), (None, True), ("-15", True)])
def test_the_boot_exit_codes(migrated_db, tmp_path, value, exits_zero):
    """The real boot path as a process. A refused value exits by itself before binding; an accepted (or absent) one
    boots, answers /health/live, and exits on SIGTERM - the code asserted is the process's own."""
    import os
    import signal
    import subprocess
    import sys

    from tests.conftest import VALID_ENV
    from tests.dbkit import BACKEND_DIR
    from tests.sea.kit import live_api

    assert "SALES_CUTOFF_MINUTES" not in os.environ  # so None really is "absent"
    if exits_zero:
        with live_api(migrated_db, tmp_path, **({"SALES_CUTOFF_MINUTES": value} if value else {})) as (_, proc):
            proc.send_signal(signal.SIGTERM)
            code = proc.wait(timeout=30)
    else:
        env = {**os.environ, **VALID_ENV, "DATABASE_URL": migrated_db.app_url, "SALES_CUTOFF_MINUTES": value,
               "PYTHONPATH": str(BACKEND_DIR)}
        code = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True,
                              text=True, timeout=30).returncode
    assert (code == 0) is exits_zero, code


# ---- the cut-off is evaluated at the hold and nowhere else: the confirm (EP-PAY-01) never re-checks it ----------


@pytest.mark.parametrize("ttl,confirm_at", [(None, "2026-08-14T19:47:00+05:30"), ("3600", "2026-08-14T20:30:00+05:30")])
async def test_a_hold_taken_before_the_cut_off_confirms_after_it(world, ttl, confirm_at):
    from tests.sea.kit import confirm, r_call

    clock = SetClock()
    clock.set("2026-08-14T19:44:59+05:30")
    customer = user(world["db"])
    async with api(world["db"], clock, **({"SEAT_HOLD_TTL_SECONDS": ttl} if ttl else {})) as c:
        held = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))
        assert held.status_code == 201, held.text
        clock.set(confirm_at)
        assert r_call("EXISTS", "lock:seat:77:402") == 1  # alive, so a 201 is the cut-off not re-checked
        booked = await confirm(c, customer, held.json()["hold_token"])
    assert booked.status_code == 201, booked.text

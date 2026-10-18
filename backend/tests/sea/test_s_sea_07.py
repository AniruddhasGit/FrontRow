"""S-SEA-07 (P-HLD-02): the hold lasts SEAT_HOLD_TTL_SECONDS, its expiry is fixed at acquisition, and Redis alone
removes the keys.

Not here: `boot exits non-zero when SEAT_HOLD_TTL_SECONDS is absent`. app/core/config.py (the config lane's file)
defaults it to 180 as PRD S7.9 publishes, so an absent value boots. The AC and S7.9 disagree; reported, not tested
against the wrong side.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import ConfigError, load_settings
from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_call, r_pttl, session, user, world77
from tests.xct._support import rg

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
APP_TREES = ("backend/app", "backend/migrations", "frontend/src", "scripts")


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


@pytest.mark.parametrize("ttl,expires,low", [("180", "2026-08-14T14:05:37.412Z", 179000), ("45", "2026-08-14T14:03:22.412Z", 44000)])
async def test_expires_at_and_every_key_ttl_come_from_configuration(world, ttl, expires, low):
    customer = user(world["db"])
    async with api(world["db"], _clock(), SEAT_HOLD_TTL_SECONDS=ttl) as c:
        r = await c.post(URL, json={"seat_ids": [402, 403]}, cookies=session(c, customer))
        pttls = [r_pttl("lock:seat:77:402"), r_pttl("lock:seat:77:403")]
    assert r.status_code == 201 and r.json()["expires_at"] == expires
    assert all(low < p <= low + 1000 for p in pttls), pttls


def test_no_seven_minute_hold_survives_anywhere_in_the_application():
    assert rg("7 minutes", *APP_TREES, fixed=True) == []


async def test_reselecting_a_held_seat_moves_nothing_and_a_later_seat_gets_the_remainder(world):
    customer = user(world["db"])
    clock = _clock()
    async with api(world["db"], clock) as c:
        first = (await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))).json()
        before = r_pttl("lock:seat:77:402")
        again = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))
        assert again.status_code == 201 and again.json()["expires_at"] == first["expires_at"]
        assert r_pttl("lock:seat:77:402") <= before
        clock.advance(60)
        later = await c.post(URL, json={"seat_ids": [403]}, cookies=session(c, customer))
        assert later.status_code == 201 and later.json()["expires_at"] == first["expires_at"]
        assert 119000 < r_pttl("lock:seat:77:403") <= 120000


async def test_the_api_offers_no_way_to_move_an_expiry(world):
    async with api(world["db"], _clock()) as c:
        doc = c.application.openapi()
    ops = sorted((m.upper(), p) for p, item in doc["paths"].items() if p.startswith("/api/holds") for m in item)
    assert ops == [("DELETE", "/api/holds/{hold_token}"), ("DELETE", "/api/holds/{hold_token}/seats/{seat_id}"),
                   ("GET", "/api/holds/{hold_token}")]

    def props(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "properties" and isinstance(v, dict):
                    yield from v
                yield from props(v)
        elif isinstance(node, list):
            for v in node:
                yield from props(v)

    bodies = [op["requestBody"] for item in doc["paths"].values() for op in item.values() if "requestBody" in op]
    refs = {b["content"]["application/json"]["schema"].get("$ref", "").rsplit("/", 1)[-1] for b in bodies}
    schemas = [doc["components"]["schemas"][r] for r in refs if r] + bodies
    assert "expires_at" not in set(props(schemas))


@pytest.mark.parametrize("ttl,delay,boots", [("abc", "1500", False), ("0", "1500", False), ("-5", "1500", False),
                                             ("180", "17999", True), ("180", "18000", False)])
def test_the_boot_check_on_the_hold_and_the_payment_delay(valid_env, ttl, delay, boots):
    valid_env.setenv("SEAT_HOLD_TTL_SECONDS", ttl)
    valid_env.setenv("PAYMENT_SIMULATED_DELAY_MS", delay)
    if boots:
        assert load_settings().SEAT_HOLD_TTL_SECONDS == 180
    else:
        with pytest.raises(ConfigError):
            load_settings()


async def test_redis_alone_removes_the_keys_when_the_ttl_elapses(world):
    customer = user(world["db"])
    async with api(world["db"], _clock(), SEAT_HOLD_TTL_SECONDS="2") as c:
        r = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))
        assert r.status_code == 201 and r_call("EXISTS", "lock:seat:77:402") == 1
        c.redis_log.reset()
        polls = 0
        while r_call("EXISTS", "lock:seat:77:402") == 1 and polls < 400:
            polls += 1
            await asyncio.sleep(0.025)  # yields to Redis's own clock; the application clock is never read
        window = list(c.redis_log.commands)
    assert r_call("EXISTS", "lock:seat:77:402") == 0
    assert not [cmd for cmd in window if cmd[0].upper() in ("DEL", "UNLINK") and "lock:seat:77:402" in cmd]
    assert rg(r"apscheduler|BackgroundScheduler|celerybeat|beat_schedule|crontab|schedule\.every", *APP_TREES,
              ignore_case=True) == []

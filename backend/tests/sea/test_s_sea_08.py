"""S-SEA-08 (P-HLD-03, EP-HLD-02): whether a hold is alive is Redis's answer, never a clock comparison.

The hold READ (GET /api/holds/{token}) is the liveness surface asserted here. Not here: the CONFIRM's 201 / 409
(EP-PAY-01 is lane PAY's and is not mounted), and the repository-wide wall-clock sweep, which finds other
lanes' sleeping polls in tests/adm, tests/xct and tests/test_shutdown.py - this module's own sweep covers tests/sea.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime

import pytest

from app.domain import holds
from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_call, session, user, world77
from tests.xct._support import REPO, rg

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
ENDED = ("The hold on your seats has ended and they have been released. You have not been charged. "
         "Choose them again if they are still free.")
BAD = "This request could not be processed. Return to the seat map and choose your seats again."


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


async def test_the_injected_clock_past_expires_at_changes_nothing_while_the_key_lives(world):
    customer = user(world["db"])
    clock = _clock()
    async with api(world["db"], clock) as c:
        cookies = session(c, customer)
        hold = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        assert hold["expires_at"] == "2026-08-14T14:05:37.412Z"
        clock.set("2026-08-14T14:05:37.412+00:00")  # exactly expires_at
        at = await c.get(f"/api/holds/{hold['hold_token']}", cookies=cookies)
        clock.advance(1)
        after = await c.get(f"/api/holds/{hold['hold_token']}", cookies=cookies)
    assert at.status_code == 200 and after.status_code == 200
    assert at.json() == after.json() == hold


async def test_gone_keys_are_hold_expired_both_ways_they_go(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        deleted = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        r_call("DEL", "lock:seat:77:402")
        by_delete = await c.get(f"/api/holds/{deleted['hold_token']}", cookies=cookies)
    assert (by_delete.status_code, by_delete.json()["error"]["code"]) == (409, "HOLD_EXPIRED")
    async with api(world["db"], _clock(), SEAT_HOLD_TTL_SECONDS="2") as c:
        cookies = session(c, customer)
        timed = (await c.post(URL, json={"seat_ids": [403]}, cookies=cookies)).json()
        polls = 0
        while r_call("EXISTS", "lock:seat:77:403") == 1 and polls < 400:
            polls += 1
            await asyncio.sleep(0.025)
        by_ttl = await c.get(f"/api/holds/{timed['hold_token']}", cookies=cookies)
    assert (by_ttl.status_code, by_ttl.json()["error"]["code"], by_ttl.json()["error"]["message"]) == (409, "HOLD_EXPIRED", ENDED)


async def test_unmatched_foreign_and_malformed_tokens(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        unmatched = await c.get("/api/holds/" + "A" * 43, cookies=cookies)
        hold = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        r_call("SET", "lock:seat:77:402", "a-different-hold-token", "PX", "300000")
        foreign = await c.get(f"/api/holds/{hold['hold_token']}", cookies=cookies)
        malformed = []
        # A 43-character token containing `/` is two path segments and reaches no route (404) - reported, not asserted.
        for token in ("A" * 42, "A" * 44, "A" * 42 + "+", "A" * 42 + "="):
            c.redis_log.reset()
            r = await c.get(f"/api/holds/{token}", cookies=cookies)
            malformed.append((r.status_code, r.json()["error"]["code"], r.json()["error"]["message"], list(c.redis_log.commands)))
    assert (unmatched.status_code, unmatched.json()["error"]["code"], unmatched.json()["error"]["message"]) == (409, "HOLD_EXPIRED", ENDED)
    assert (foreign.status_code, foreign.json()["error"]["code"], foreign.json()["error"]["message"]) == (403, "HOLD_NOT_OWNED", ENDED)
    assert malformed == [(400, "REQUEST_INVALID", BAD, [])] * 4


async def test_the_liveness_check_takes_no_clock_and_sends_one_get(world):
    sig = inspect.signature(holds.liveness)
    assert not {"now", "clock", "at", "instant"} & set(sig.parameters)
    assert not [p for p in sig.parameters.values() if p.annotation in (datetime, "datetime")]
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        hold = (await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))).json()
        redis = c.application.state.redis
        c.redis_log.reset()
        assert await holds.liveness(redis, 77, [402], hold["hold_token"]) == "live"
        assert c.redis_log.commands == [("GET", "lock:seat:77:402")]


async def test_the_read_takes_no_client_instant(world):
    contract = json.loads((REPO / "docs/03 PRD/api/contract.json").read_text(encoding="utf-8"))
    entry = next(e for e in contract["endpoints"] if e["id"] == "EP-HLD-02")
    assert entry["request"]["query"] == {} and entry["request"]["body"] == {}
    async with api(world["db"], _clock()) as c:
        op = c.application.openapi()["paths"]["/api/holds/{hold_token}"]["get"]
    assert "requestBody" not in op
    assert [p["in"] for p in op.get("parameters", [])] == ["path"]


def test_no_test_in_this_lane_reads_the_wall_clock():
    assert rg(r"time\.sleep\(|datetime\.now\(|datetime\.utcnow\(|time\.time\(", "backend/tests/sea") == []

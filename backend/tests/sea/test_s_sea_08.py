"""S-SEA-08 (P-HLD-03, EP-HLD-02, EP-PAY-01): whether a hold is alive is Redis's answer, never a clock comparison.

Both liveness surfaces are asserted: the hold READ (GET /api/holds/{token}) and the CONFIRM (POST /api/bookings).
A 43-character token carrying `/` is two path segments and reaches no route; the application's not-found handler
answers it with the same 400 (CR-002 B-13, Q-R3-05). The wall-clock sweep covers all of backend/tests (CR-002 A-5).
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
        # 42, 44, and 43 carrying `+`, `/` or `=`. The `/` one is two path segments: the not-found handler (CR-002 B-13).
        for token in ("A" * 42, "A" * 44, "A" * 42 + "+", "A" * 21 + "/" + "A" * 21, "A" * 42 + "="):
            c.redis_log.reset()
            r = await c.get(f"/api/holds/{token}", cookies=cookies)
            malformed.append((r.status_code, r.json()["error"]["code"], r.json()["error"]["message"], list(c.redis_log.commands)))
    assert (unmatched.status_code, unmatched.json()["error"]["code"], unmatched.json()["error"]["message"]) == (409, "HOLD_EXPIRED", ENDED)
    assert (foreign.status_code, foreign.json()["error"]["code"], foreign.json()["error"]["message"]) == (403, "HOLD_NOT_OWNED", ENDED)
    assert malformed == [(400, "REQUEST_INVALID", BAD, [])] * 5


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


def _bounded(loop) -> bool:
    """A for over range(...), or a while whose test compares a counter the body increments."""
    import ast

    if isinstance(loop, ast.For):
        return isinstance(loop.iter, ast.Call) and getattr(loop.iter.func, "id", None) == "range"
    counted = {n.target.id for n in ast.walk(loop) if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)}
    return any(isinstance(c, ast.Compare) and isinstance(c.left, ast.Name) and c.left.id in counted
               and all(isinstance(op, (ast.Lt, ast.LtE)) for op in c.ops) for c in ast.walk(loop.test))


def test_no_test_in_this_lane_reads_the_wall_clock():
    """CR-002 A-5, over all of backend/tests."""
    import ast

    assert rg(r"datetime\.now\(|datetime\.utcnow\(|datetime\.today\(|date\.today\(|time\.time\(|time\.time_ns\(",
              "backend/tests") == []
    sleeps = rg(r"time\.sleep\(", "backend/tests")
    assert sleeps, "no sleep found - a vacuous pass is not a pass"
    unbounded = []
    for path in sorted({h[0] for h in sleeps}):
        tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "time.sleep":
                loop = parents.get(node)
                while loop is not None and not isinstance(loop, (ast.For, ast.While, ast.FunctionDef, ast.AsyncFunctionDef)):
                    loop = parents.get(loop)
                if not isinstance(loop, (ast.For, ast.While)) or not _bounded(loop):
                    unbounded.append(f"{path}:{node.lineno}")
    assert unbounded == []
    # The check itself: a clock-bounded loop and a bare sleep are both caught.
    clocked = ast.parse("while time.monotonic() < end:\n    time.sleep(0.1)\n").body[0]
    counted = ast.parse("while x and polls < 100:\n    polls += 1\n    time.sleep(0.1)\n").body[0]
    assert not _bounded(clocked) and _bounded(counted) and _bounded(ast.parse("for _ in range(9):\n    pass\n").body[0])


# ---- the confirm (EP-PAY-01) as the liveness surface ------------------------------------------------------


async def test_the_confirm_is_201_while_the_keys_live_and_hold_expired_once_they_go(world):
    from tests.sea.kit import confirm

    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        cookies = session(c, customer)
        live = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        ok = await confirm(c, customer, live["hold_token"])
        deleted = (await c.post(URL, json={"seat_ids": [404]}, cookies=cookies)).json()
        r_call("DEL", "lock:seat:77:404")
        by_delete = await confirm(c, customer, deleted["hold_token"])
    async with api(world["db"], _clock(), SEAT_HOLD_TTL_SECONDS="2") as c:
        timed = (await c.post(URL, json={"seat_ids": [403]}, cookies=session(c, customer))).json()
        polls = 0
        while r_call("EXISTS", "lock:seat:77:403") == 1 and polls < 400:  # Redis's own TTL, never the app clock
            polls += 1
            await asyncio.sleep(0.025)
        by_ttl = await confirm(c, customer, timed["hold_token"])
    assert ok.status_code == 201, ok.text
    for r in (by_delete, by_ttl):
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, "HOLD_EXPIRED", ENDED)


async def test_the_confirm_ignores_the_injected_clock_at_and_past_expires_at(world):
    """The assertion that proves no clock is compared: at expires_at and at expires_at + 1 s on the INJECTED clock,
    with the keys still present in Redis, the confirm is 201 and never 409 HOLD_EXPIRED."""
    from tests.sea.kit import confirm

    customer = user(world["db"])
    clock = _clock()
    async with api(world["db"], clock) as c:
        cookies = session(c, customer)
        at = (await c.post(URL, json={"seat_ids": [402]}, cookies=cookies)).json()
        past = (await c.post(f"/api/showtimes/88/holds", json={"seat_ids": [402]}, cookies=cookies)).json()
        assert at["expires_at"] == past["expires_at"] == "2026-08-14T14:05:37.412Z"
        clock.set("2026-08-14T14:05:37.412+00:00")
        r_at = await confirm(c, customer, at["hold_token"])
        clock.advance(1)
        r_past = await confirm(c, customer, past["hold_token"], showtime_id=88)
    assert (r_at.status_code, r_past.status_code) == (201, 201), (r_at.text, r_past.text)

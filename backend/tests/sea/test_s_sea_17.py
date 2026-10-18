"""S-SEA-17 (P-HLD-12, FR-ADR-033): release this instance's holds at shutdown, and never depend on it.

HERE: the registry, and the lifespan shutdown hook run exactly as uvicorn runs it after the drain - in-process.
The REAL SIGTERM to a running container, the SIGKILL that skips the hook, and exit code 0 are the host drill
backend/tests/sea/drill_live.py (stages `sigterm` and `sigkill`). Not here: a confirm in flight at SIGTERM
(EP-PAY-01, lane PAY, is not mounted).
"""

from __future__ import annotations

import pytest

from app.core import locks
from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_call, r_pttl, session, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


async def test_the_registry_lists_every_key_this_instance_granted_with_the_holds_ttl(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        c.application.state.instance_id = "i-1"
        r = await c.post(URL, json={"seat_ids": [402, 403]}, cookies=session(c, customer))
        members = r_call("SMEMBERS", "instance:i-1:holds")
        registry_ttl, key_ttl = r_pttl("instance:i-1:holds"), r_pttl("lock:seat:77:402")
    assert r.status_code == 201 and members == {"lock:seat:77:402", "lock:seat:77:403"}
    assert abs(registry_ttl - key_ttl) <= 1000


async def test_shutdown_releases_this_instances_holds_and_nothing_else(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        c.application.state.instance_id = "i-1"
        hold = (await c.post(URL, json={"seat_ids": [402, 403]}, cookies=session(c, customer))).json()
        # A key in the registry now carrying another hold's token (expired and re-taken): must be left alone.
        r_call("SET", "lock:seat:77:403", "another-holds-token", "PX", "300000")
        r_call("SET", "cache:seatmap:77", "stale", "EX", "60")
    # The lifespan has exited: the drain is over and the hooks ran.
    assert r_call("EXISTS", "lock:seat:77:402") == 0
    assert r_call("GET", "lock:seat:77:403") == "another-holds-token"
    assert r_call("EXISTS", f"hold:{hold['hold_token']}") == 0
    assert r_call("SCARD", f"holds:user:{customer}:showtime:77") == 0
    assert r_call("EXISTS", "cache:seatmap:77") == 0 and r_call("EXISTS", "instance:i-1:holds") == 0
    async with api(world["db"], _clock()) as c:
        again = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, customer))
    assert again.status_code == 201


async def test_the_release_is_best_effort_per_key(world, monkeypatch):
    customer = user(world["db"])
    real = locks.release

    async def flaky(redis, key, token):
        if key == "lock:seat:77:403":
            raise ConnectionError("this one key's compare-and-delete fails")
        return await real(redis, key, token)

    async with api(world["db"], _clock()) as c:
        c.application.state.instance_id = "i-1"
        hold = (await c.post(URL, json={"seat_ids": [402, 403, 404]}, cookies=session(c, customer))).json()
        monkeypatch.setattr(locks, "release", flaky)
    assert r_call("EXISTS", "lock:seat:77:402") == 0 and r_call("EXISTS", "lock:seat:77:404") == 0
    assert r_call("GET", "lock:seat:77:403") == hold["hold_token"]

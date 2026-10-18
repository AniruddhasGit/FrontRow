"""S-SEA-17 (P-HLD-12, FR-ADR-033): release this instance's holds at shutdown, and never depend on it.

HERE: the registry, the lifespan shutdown hook run exactly as uvicorn runs it after the drain - in-process - and a
confirm in flight when a REAL SIGTERM reaches a REAL api process (tests/drain_harness.py) inside the test image.
The SIGTERM to a running CONTAINER and the SIGKILL that skips the hook are the host drill
backend/tests/sea/drill_live.py (stages `sigterm` and `sigkill`).
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



def test_a_confirm_in_flight_when_sigterm_arrives_completes_and_commits(migrated_db, tmp_path):
    """A REAL process (the real boot path, tests/drain_harness.py) and a REAL SIGTERM, inside the test image. The
    confirm is observed in flight - its transaction open in pg_stat_activity during the simulated payment delay -
    when the signal is sent; it still answers 201, its booking_seat row is committed, and the process exits 0."""
    import os
    import signal
    import threading
    from urllib.parse import urlsplit

    import httpx

    from tests.dbkit import run_sql
    from tests.sea.kit import live_api, live_cookie, one

    # Starts in 2099 so the process's real clock is before the sales cut-off; no line of this test reads a clock.
    world77(migrated_db, starts="2099-01-01T19:30:00+05:30")
    cookies = live_cookie(migrated_db, user(migrated_db))
    result: dict = {}
    with live_api(migrated_db, tmp_path, PAYMENT_SIMULATED_DELAY_MS="3000") as (base, proc):
        hold = httpx.post(f"{base}/api/showtimes/77/holds", json={"seat_ids": [402]}, cookies=cookies, timeout=10)
        assert hold.status_code == 201, hold.text

        def in_flight() -> None:
            r = httpx.post(f"{base}/api/bookings", json={"hold_token": hold.json()["hold_token"], "showtime_id": 77},
                           headers={"Idempotency-Key": "sigterm-1"}, cookies=cookies, timeout=30)
            result["status"], result["body"] = r.status_code, r.text

        worker = threading.Thread(target=in_flight)
        worker.start()
        dbname, open_tx = urlsplit(migrated_db.app_url).path.lstrip("/"), 0
        for _ in range(200):
            open_tx = run_sql(os.environ["TEST_ADMIN_DATABASE_URL"],
                              "SELECT count(*) FROM pg_stat_activity WHERE datname = %s AND usename = 'frontrow_app' "
                              "AND state = 'idle in transaction'", (dbname,))[0][0]
            if open_tx:
                break
            threading.Event().wait(0.02)
        assert open_tx == 1, "the confirm was never observed inside its transaction"
        assert "status" not in result
        proc.send_signal(signal.SIGTERM)
        worker.join(timeout=30)
        code = proc.wait(timeout=30)
        log = proc.log()
    assert result.get("status") == 201, (result, log)
    assert code == 0, log
    assert one(migrated_db, "SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = 402") == 1

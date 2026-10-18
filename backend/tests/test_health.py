"""P-XCT-10 / SRC-002 §7.4: /health/live and /health/ready behave differently, on purpose.

These tests use fake probes. They prove the handler logic. They do NOT prove the timeouts against a
real stopped container -- PRD S7.7 says only stopping the container proves that, and the GOAL_14
gate does it with `docker compose stop`.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.readiness import Probe, Readiness
from app.main import create_app

from .conftest import VALID_ENV


class Calls:
    def __init__(self) -> None:
        self.n = 0


def ok_probe(name: str, calls: Calls | None = None) -> Probe:
    async def check() -> None:
        if calls is not None:
            calls.n += 1

    return Probe(name=name, check=check, timeout_s=0.5)


def failing_probe(name: str) -> Probe:
    async def check() -> None:
        raise ConnectionRefusedError(f"{name} refused")

    return Probe(name=name, check=check, timeout_s=0.5)


def exploding_probe(name: str) -> Probe:
    """A probe that fails the test if anything calls it."""

    async def check() -> None:
        raise AssertionError(f"/health/live touched {name}")

    return Probe(name=name, check=check, timeout_s=0.5)


def hanging_probe(name: str, timeout_s: float = 0.05) -> Probe:
    async def check() -> None:
        await asyncio.sleep(3600)

    return Probe(name=name, check=check, timeout_s=timeout_s)


@pytest.fixture
def settings(valid_env) -> Settings:
    return Settings(**VALID_ENV)


def client_for(settings, clock, probes) -> TestClient:
    return TestClient(create_app(settings, clock=clock, probes=probes))


# ---------------------------------------------------------------- /health/live


def test_live_returns_200_and_fixed_body(settings, clock, log_capture):
    with client_for(settings, clock, [ok_probe("postgres"), ok_probe("redis")]) as c:
        r = c.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "live"}


def test_live_touches_no_dependency(settings, clock, log_capture):
    with client_for(settings, clock, [exploding_probe("postgres"), exploding_probe("redis")]) as c:
        for _ in range(3):
            assert c.get("/health/live").status_code == 200


def test_live_is_200_while_both_dependencies_are_down(settings, clock, log_capture):
    with client_for(settings, clock, [failing_probe("postgres"), failing_probe("redis")]) as c:
        assert c.get("/health/ready").status_code == 503
        assert c.get("/health/live").status_code == 200


# ---------------------------------------------------------------- /health/ready


def test_ready_200_when_both_dependencies_answer(settings, clock, log_capture):
    with client_for(settings, clock, [ok_probe("postgres"), ok_probe("redis")]) as c:
        r = c.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}


@pytest.mark.parametrize("down", ["postgres", "redis"])
def test_ready_503_naming_the_dependency_that_is_down(settings, clock, log_capture, down):
    up = "redis" if down == "postgres" else "postgres"
    with client_for(settings, clock, [failing_probe(down), ok_probe(up)]) as c:
        r = c.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"][down] == "unreachable"
    assert body["checks"][up] == "ok"


def test_ready_503_naming_both(settings, clock, log_capture):
    with client_for(settings, clock, [failing_probe("postgres"), failing_probe("redis")]) as c:
        r = c.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"postgres": "unreachable", "redis": "unreachable"}


def test_ready_body_leaks_nothing_sensitive(settings, clock, log_capture):
    with client_for(settings, clock, [failing_probe("postgres"), ok_probe("redis")]) as c:
        text = c.get("/health/ready").text
    for secret_shaped in ("pw", "db.invalid", "cache.invalid", "refused", "Error"):
        assert secret_shaped not in text


def test_a_hanging_probe_fails_fast_on_its_own_timeout(settings, clock, log_capture):
    with client_for(settings, clock, [hanging_probe("postgres"), ok_probe("redis")]) as c:
        r = c.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["postgres"] == "unreachable"


# ---------------------------------------------------------------- the readiness cache


def test_result_is_cached_for_the_ttl_then_reprobed(clock):
    calls = Calls()
    readiness = Readiness([ok_probe("postgres", calls), ok_probe("redis")], ttl_s=3, clock=clock)

    async def scenario():
        await readiness.check()
        clock.advance(2.9)
        await readiness.check()
        first = calls.n
        clock.advance(0.2)  # now 3.1 s after the first probe: stale
        await readiness.check()
        return first, calls.n

    first, second = asyncio.run(scenario())
    assert first == 1
    assert second == 2


def test_ttl_zero_means_every_poll_probes(clock):
    calls = Calls()
    readiness = Readiness([ok_probe("postgres", calls)], ttl_s=0, clock=clock)

    async def scenario():
        for _ in range(3):
            await readiness.check()

    asyncio.run(scenario())
    assert calls.n == 3


def test_concurrent_stale_polls_probe_once(clock):
    """Two load balancer polls landing together must not both open a database connection."""
    calls = Calls()

    async def slow_check() -> None:
        calls.n += 1
        await asyncio.sleep(0.05)

    readiness = Readiness([Probe("postgres", slow_check, 1.0)], ttl_s=3, clock=clock)

    async def scenario():
        await asyncio.gather(*(readiness.check() for _ in range(5)))

    asyncio.run(scenario())
    assert calls.n == 1


def test_a_failed_result_is_cached_too(clock):
    """Otherwise an outage turns every poll into a fresh timeout-length probe."""
    calls = Calls()

    async def check() -> None:
        calls.n += 1
        raise ConnectionRefusedError

    readiness = Readiness([Probe("redis", check, 0.5)], ttl_s=3, clock=clock)

    async def scenario():
        a = await readiness.check()
        b = await readiness.check()
        return a, b

    a, b = asyncio.run(scenario())
    assert not a.ok and not b.ok
    assert calls.n == 1

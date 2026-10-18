"""Helpers the account-lane tests share.

Every HTTP call goes through httpx's ASGI transport on the test's own event loop, which runs on the
main thread. That is what makes S-ACC-02's "bcrypt runs off the event loop" assertion meaningful: with
Starlette's TestClient the app runs on a portal thread, so "not the main thread" would prove nothing.

Time is injected (SetClock); nothing here reads the wall clock.
"""

from __future__ import annotations

import base64
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import pytest

from app.core.security import SESSION_COOKIE
from app.main import create_app
from tests.conftest import FakeClock
from tests.dbkit import app_settings
from tests.test_health import ok_probe


class SetClock(FakeClock):
    """FakeClock that can also be put at an exact instant (S-ACC-05's worked example)."""

    def set(self, instant: datetime) -> None:
        self._mono += max(0.0, (instant - self._now).total_seconds())
        self._now = instant


def redis_url() -> str:
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.fail("TEST_REDIS_URL is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return url


def flush_redis() -> None:
    """Every test starts with empty buckets. TEST_REDIS_URL names a database number of its own."""
    import redis

    client = redis.Redis.from_url(redis_url())
    try:
        client.flushdb()
    finally:
        client.close()


def redis_pttl_of_keys(pattern: str) -> dict[str, int]:
    import redis

    client = redis.Redis.from_url(redis_url())
    try:
        return {k.decode(): client.pttl(k) for k in client.scan_iter(match=pattern)}
    finally:
        client.close()


def settings_for(db, **overrides: str):
    """The app's settings for one throwaway database. BCRYPT_COST=4 is bcrypt's minimum, for speed."""
    return app_settings(db, **{"REDIS_URL": redis_url(), "BCRYPT_COST": "4", **overrides})


@asynccontextmanager
async def api(settings, clock, client_addr: tuple[str, int] = ("127.0.0.1", 50000), wrap=None):
    """The real application with its lifespan running, and an httpx client bound to it."""
    application = create_app(settings, clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    asgi = wrap(application) if wrap else application
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=asgi, client=client_addr)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            client.application = application  # type: ignore[attr-defined]
            yield client


def session_cookie(response: httpx.Response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        name, _, rest = header.partition("=")
        if name == SESSION_COOKIE:
            return rest.split(";", 1)[0]
    return None


def cookie_attributes(header: str) -> dict[str, str]:
    """{'httponly': '', 'samesite': 'lax', ...} for one Set-Cookie header; names lowercased."""
    out = {}
    for part in header.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        out[name.lower()] = value
    return out


def jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def without_request_id(body: dict) -> dict:
    error = dict(body["error"])
    error.pop("request_id")
    return {**body, "error": error}

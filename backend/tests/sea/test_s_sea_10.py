"""S-SEA-10 (P-HLD-05): the guest is stopped at the hold, on the router, and nowhere else.

Not here (browser harness): the primary action's two labels, the sessionStorage write before sign-in, the request
spy reporting zero calls, and the restored selection on return.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.api import holds as holds_api
from app.core.security import SESSION_COOKIE, issue_session_token
from app.domain import holds
from tests.sea.kit import SHOWTIME, T0, SetClock, api, r_keys, session, user, world77

pytestmark = pytest.mark.anyio
URL = f"/api/showtimes/{SHOWTIME}/holds"
SIGN_IN = "Sign in to hold seats. Your selection has been kept."


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


def _clock() -> SetClock:
    c = SetClock()
    c.set(T0)
    return c


def _err(r) -> tuple:
    return r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]


async def test_no_session_and_an_expired_session_are_the_same_401_and_hold_nothing(world):
    customer = user(world["db"])
    async with api(world["db"], _clock()) as c:
        before = r_keys("lock:seat:77:*")
        none = await c.post(URL, json={"seat_ids": [402]})
        stale = issue_session_token(user_id=customer, role="customer", password_version=1,
                                    now=c.clock.now() - timedelta(seconds=c.settings.SESSION_TTL_SECONDS + 60), settings=c.settings)
        expired = await c.post(URL, json={"seat_ids": [402]}, cookies={SESSION_COOKIE: stale})
        assert r_keys("lock:seat:77:*") == before
        seatmap = await c.get(f"/api/showtimes/{SHOWTIME}/seatmap")
    assert _err(none) == _err(expired) == (401, "AUTH_REQUIRED", SIGN_IN)
    assert seatmap.status_code == 200


async def test_the_check_is_the_routers_and_survives_an_empty_handler(world, monkeypatch):
    async def bare(*args, **kwargs):
        return {}

    monkeypatch.setattr(holds, "acquire", bare)
    async with api(world["db"], _clock()) as c:
        r = await c.post(URL, json={"seat_ids": [402]})
    assert _err(r) == (401, "AUTH_REQUIRED", SIGN_IN)
    assert any(d.dependency is holds_api.signed_in for d in holds_api.router.dependencies)


@pytest.mark.parametrize("role", ["customer", "manager", "admin"])
async def test_every_signed_in_role_may_hold(world, role):
    who = user(world["db"], role)
    async with api(world["db"], _clock()) as c:
        r = await c.post(URL, json={"seat_ids": [402]}, cookies=session(c, who, role))
    assert r.status_code == 201, r.text

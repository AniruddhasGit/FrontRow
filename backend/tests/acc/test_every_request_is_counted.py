"""P-XCT-07 'every request counted' on the account endpoints: a body whose fields have the wrong JSON type is
counted by the limiter before it is refused, like any other malformed request (verifier finding, Phase 2).
A body that is not JSON at all is still refused by the framework before the handler runs - see the lane report."""

from __future__ import annotations

import pytest

from tests.acc._support import api, flush_redis, settings_for

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()
    yield
    flush_redis()


@pytest.mark.parametrize("body", [{"email": 1, "password": "long enough password"}, {"email": "a@b.example", "password": []}])
async def test_a_wrongly_typed_register_body_is_counted_then_refused(migrated_db, clock, body):
    async with api(settings_for(migrated_db, RATE_LIMIT_REGISTER_IP_PER_HOUR="2"), clock) as c:
        codes = [(await c.post("/api/auth/register", json=body)).status_code for _ in range(3)]
    assert codes == [422, 422, 429]


@pytest.mark.parametrize("body", [{"email": 1, "password": "x"}, {"email": "a@b.example", "password": 7}])
async def test_a_wrongly_typed_login_body_is_counted_then_refused(migrated_db, clock, body):
    async with api(settings_for(migrated_db, RATE_LIMIT_LOGIN_IP_PER_15MIN="2"), clock) as c:
        codes = [(await c.post("/api/auth/login", json=body)).status_code for _ in range(3)]
    assert codes[:2] == [422, 422] and codes[2] == 429

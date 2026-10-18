"""S-ACC-09 - the credential endpoints' token buckets: Retry-After from the refill rate, the injected
clock, the real client address, and failing closed (P-ACC-14, FR-ADR-058, EP-ACC-01/02).

NOT covered here: the reset-request and reset-confirm buckets (the 6th reset request, the 11th
confirm, the separate confirm bucket, a token spent by every confirm). EP-ACC-05/06 ship in Phase 5
(SRC-004 JC-R6-02) and are asserted there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core import ratelimit
from tests.acc._support import api, flush_redis, redis_pttl_of_keys, settings_for

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
PER_EMAIL = "Too many sign-in attempts for that email address. Try again in {} seconds."


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


def _login(email: str, password: str = "wrong horse battery") -> dict:
    return {"email": email, "password": password}


def _error(r) -> tuple[int, str, str, str | None]:
    e = r.json()["error"]
    return r.status_code, e["code"], e["message"], r.headers.get("retry-after")


async def test_the_11th_sign_in_for_one_email_is_refused_with_retry_after_90(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        codes = [(await c.post("/api/auth/login", json=_login("Target@example.com"))).status_code for _ in range(10)]
        eleventh = await c.post("/api/auth/login", json=_login("  target@EXAMPLE.com"))
    assert codes == [401] * 10
    assert _error(eleventh) == (429, "RATE_LIMITED", PER_EMAIL.format(90), "90")


async def test_the_31st_sign_in_from_one_ip_is_refused_by_the_ip_bucket(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        codes = [(await c.post("/api/auth/login", json=_login(f"user{i}@example.com"))).status_code for i in range(30)]
        last = await c.post("/api/auth/login", json=_login("user30@example.com"))
    assert codes == [401] * 30
    assert _error(last) == (429, "RATE_LIMITED", "Too many sign-in attempts from this connection. Try again in 30 seconds.", "30")


async def test_the_6th_registration_from_one_ip_in_an_hour_waits_12_minutes(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        codes = [(await c.post("/api/auth/register", json={"email": f"reg{i}@example.com", "password": PASSWORD})).status_code
                 for i in range(5)]
        sixth = await c.post("/api/auth/register", json={"email": "reg5@example.com", "password": PASSWORD})
    assert codes == [201] * 5
    assert _error(sixth) == (429, "RATE_LIMITED", "Too many accounts have been created from this connection. "
                                                  "Try again in 12 minutes.", "720")


async def test_retry_after_is_the_time_to_the_next_token_not_a_constant(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        for _ in range(10):
            await c.post("/api/auth/login", json=_login("drain@example.com"))
        at_zero = await c.post("/api/auth/login", json=_login("drain@example.com"))
        clock.advance(30)
        at_thirty = await c.post("/api/auth/login", json=_login("drain@example.com"))
    assert at_zero.headers["retry-after"] == "90"
    assert _error(at_thirty) == (429, "RATE_LIMITED", PER_EMAIL.format(60), "60")


async def test_refill_follows_the_injected_clock_and_the_key_ttl_is_only_a_backstop(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        for _ in range(10):
            await c.post("/api/auth/login", json=_login("refill@example.com"))
        refused = await c.post("/api/auth/login", json=_login("refill@example.com"))
        clock.advance(90)
        admitted = await c.post("/api/auth/login", json=_login("refill@example.com"))
        ttls = redis_pttl_of_keys("rl:login-email:*")
    assert refused.status_code == 429
    assert admitted.status_code == 401  # admitted by the limiter; the password is still wrong
    assert ttls and all(ttl > 0 for ttl in ttls.values()), ttls


def test_the_lua_script_never_asks_redis_for_the_time():
    assert "TIME" not in Path(ratelimit.__file__).read_text(encoding="utf-8")


async def test_forged_leftmost_forwarded_for_values_share_the_real_clients_bucket(migrated_db, clock):
    # The load balancer is the one trusted proxy (FORWARDED_ALLOW_IPS); it appends the real client.
    settings = settings_for(migrated_db, FORWARDED_ALLOW_IPS="10.0.0.2")
    async with api(settings, clock, client_addr=("10.0.0.2", 40000)) as c:
        for i in range(30):
            forged = f"198.51.100.{i}, 203.0.113.7"  # a different forged leftmost entry every time
            await c.post("/api/auth/login", json=_login(f"xff{i}@example.com"), headers={"X-Forwarded-For": forged})
        refused = await c.post("/api/auth/login", json=_login("xff30@example.com"),
                               headers={"X-Forwarded-For": "192.0.2.99, 203.0.113.7"})
        other_client = await c.post("/api/auth/login", json=_login("xff31@example.com"),
                                    headers={"X-Forwarded-For": "192.0.2.99, 203.0.113.8"})
    assert refused.status_code == 429 and refused.json()["error"]["message"].endswith("from this connection. Try again in 30 seconds.")
    assert other_client.status_code == 401  # a different real client has its own bucket


async def test_the_same_holds_when_uvicorn_rewrites_the_peer_from_the_header(migrated_db, clock):
    """If Phase 7 turns on uvicorn's --proxy-headers, the key must not change."""
    settings = settings_for(migrated_db, FORWARDED_ALLOW_IPS="10.0.0.2")
    wrap = lambda a: ProxyHeadersMiddleware(a, trusted_hosts="10.0.0.2")  # noqa: E731
    async with api(settings, clock, client_addr=("10.0.0.2", 40000), wrap=wrap) as c:
        for i in range(30):
            await c.post("/api/auth/login", json=_login(f"uv{i}@example.com"), headers={"X-Forwarded-For": f"198.51.100.{i}, 203.0.113.7"})
        refused = await c.post("/api/auth/login", json=_login("uv30@example.com"), headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
    assert refused.status_code == 429


async def test_an_untrusted_peer_cannot_choose_its_bucket_with_the_header(migrated_db, clock):
    async with api(settings_for(migrated_db, FORWARDED_ALLOW_IPS="10.0.0.2"), clock, client_addr=("203.0.113.50", 1)) as c:
        for i in range(30):
            await c.post("/api/auth/login", json=_login(f"direct{i}@example.com"), headers={"X-Forwarded-For": f"198.51.100.{i}"})
        refused = await c.post("/api/auth/login", json=_login("direct30@example.com"), headers={"X-Forwarded-For": "192.0.2.1"})
    assert refused.status_code == 429


async def test_either_empty_bucket_alone_refuses(migrated_db, clock):
    async with api(settings_for(migrated_db, RATE_LIMIT_LOGIN_IP_PER_15MIN="12"), clock) as c:
        for _ in range(10):
            await c.post("/api/auth/login", json=_login("both@example.com"))
        email_empty = await c.post("/api/auth/login", json=_login("both@example.com"))      # IP has 2 left
        ok_other = await c.post("/api/auth/login", json=_login("fresh1@example.com"))       # IP has 1 left
        ok_other2 = await c.post("/api/auth/login", json=_login("fresh2@example.com"))      # IP has 0 left
        ip_empty = await c.post("/api/auth/login", json=_login("fresh3@example.com"))       # email bucket full
    assert email_empty.status_code == 429 and "for that email address" in email_empty.json()["error"]["message"]
    assert (ok_other.status_code, ok_other2.status_code) == (401, 401)
    assert ip_empty.status_code == 429 and "from this connection" in ip_empty.json()["error"]["message"]


async def test_with_redis_unreachable_sign_in_fails_closed_and_browsing_still_works(migrated_db, clock):
    # A closed port on the compose Redis host: the same refusal a stopped Redis gives this process.
    dead = re.sub(r":\d+/", ":1/", settings_for(migrated_db).REDIS_URL)
    async with api(settings_for(migrated_db, REDIS_URL=dead), clock) as c:
        login = await c.post("/api/auth/login", json=_login("redisdown@example.com", PASSWORD))
        register = await c.post("/api/auth/register", json={"email": "redisdown@example.com", "password": PASSWORD})
        movies = await c.get("/api/movies")  # EP-BRW-01 - the browse lane's endpoint, RED until it exists
    assert _error(login)[:3] == (503, "DEPENDENCY_UNAVAILABLE",
                                 "Sign-in is unavailable right now. Browsing still works. Try again shortly.")
    assert _error(register)[:3] == (503, "DEPENDENCY_UNAVAILABLE",
                                    "Registration is unavailable right now. Browsing still works. Try again shortly.")
    assert movies.status_code == 200


def test_spans_render_by_s7_20():
    assert [ratelimit.render_span(s) for s in (1, 3, 30, 90, 119, 120, 240, 360, 720, 900)] == [
        "1 second", "3 seconds", "30 seconds", "90 seconds", "119 seconds", "2 minutes", "4 minutes",
        "6 minutes", "12 minutes", "15 minutes"]

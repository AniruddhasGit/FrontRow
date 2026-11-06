"""S-XCT-16 (P-XCT-07, S7.4, S7.20): Retry-After is ceil(window / capacity) of the bucket that refused, never typed.

Each bucket at its S7.4 default is emptied on the injected clock (no refill between requests) and its refusal read.
The sign-in, registration and reset sentences are the account rows' published copy (P-ACC-02 rows 4-5, P-ACC-01,
P-ACC-07 row 4), which differ from this criterion's 'Too many attempts.' prefix - a PRD-vs-Bible conflict filed as a
doc defect; the computed span, the header and the absence of 720 are asserted exactly as the criterion states.
"""

from __future__ import annotations

import re

import pytest

from tests.acc._support import api as acc_api
from tests.acc._support import flush_redis, settings_for
from tests.pay import kit
from tests.xct.test_s_xct_14 import SHOWTIME, world41

pytestmark = pytest.mark.anyio


def _assert_integer_header(r) -> int:
    assert not re.search(r"[a-zA-Z]", r.headers["retry-after"])
    return int(r.headers["retry-after"])


async def test_seat_hold_per_user_20_per_60s_is_3_seconds(migrated_db):
    world41(migrated_db)
    u = kit.user(migrated_db)
    async with kit.api(migrated_db, kit.clock_at()) as c:
        rs = [await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [310]}, cookies=kit.cookies(c, u)) for _ in range(21)]
    r = rs[-1]
    assert [x.status_code for x in rs].count(429) == 1 and r.status_code == 429
    assert _assert_integer_header(r) == 3
    assert r.json()["error"]["message"] == "Too many attempts. Try again in 3 seconds."


async def test_seat_hold_per_ip_60_per_60s_is_1_second_singular(migrated_db):
    world41(migrated_db)
    users = [kit.user(migrated_db) for _ in range(61)]
    async with kit.api(migrated_db, kit.clock_at()) as c:
        rs = [await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [310]}, cookies=kit.cookies(c, u)) for u in users]
    r = rs[-1]
    assert [x.status_code for x in rs].count(429) == 1 and r.status_code == 429
    assert _assert_integer_header(r) == 1
    assert r.json()["error"]["message"] == "Too many attempts. Try again in 1 second."


def _login(email: str) -> dict:
    return {"email": email, "password": "wrong horse battery"}


async def test_sign_in_per_ip_30_per_900s_is_30_seconds(migrated_db, clock):
    flush_redis()
    async with acc_api(settings_for(migrated_db), clock) as c:
        rs = [await c.post("/api/auth/login", json=_login(f"ip{i}@example.com")) for i in range(31)]
    r = rs[-1]
    assert r.status_code == 429 and _assert_integer_header(r) == 30
    assert r.json()["error"]["message"].endswith("Try again in 30 seconds.")


async def test_sign_in_per_user_10_per_900s_is_90_seconds(migrated_db, clock):
    flush_redis()
    async with acc_api(settings_for(migrated_db), clock) as c:
        rs = [await c.post("/api/auth/login", json=_login("same@example.com")) for _ in range(11)]
    r = rs[-1]
    assert r.status_code == 429 and _assert_integer_header(r) == 90
    assert r.json()["error"]["message"].endswith("Try again in 90 seconds.")


async def test_registration_5_per_3600s_is_720_rendered_as_12_minutes(migrated_db, clock):
    flush_redis()
    async with acc_api(settings_for(migrated_db), clock) as c:
        rs = [await c.post("/api/auth/register", json={"email": f"r{i}@example.com", "password": "correct horse battery"})
              for i in range(6)]
    r = rs[-1]
    assert r.status_code == 429 and _assert_integer_header(r) == 720
    message = r.json()["error"]["message"]
    assert message.endswith("Try again in 12 minutes.") and "720" not in message


async def test_password_reset_request_5_per_3600s_is_720_rendered_as_12_minutes(migrated_db, clock):
    flush_redis()
    async with acc_api(settings_for(migrated_db), clock) as c:
        rs = [await c.post("/api/auth/password-reset/request", json={"email": f"p{i}@example.com"}) for i in range(6)]
    r = rs[-1]
    assert r.status_code == 429 and _assert_integer_header(r) == 720
    message = r.json()["error"]["message"]
    assert message == "Too many reset requests from this connection. Try again in 12 minutes." and "720" not in message

"""S-ACC-03 - sign in, record the sign-in instant, answer identically for an unknown address
(P-ACC-02, EP-ACC-02)."""

from __future__ import annotations

import pytest

from app.core import security
from tests.acc._support import api, flush_redis, session_cookie, settings_for, without_request_id
from tests.dbkit import app_sql, insert_user

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
MISMATCH = "That email address and password do not match an account."
IMMUTABLE = "SELECT email, password_hash, role, password_version, created_at FROM users WHERE id = %s"
SEVEN = {"id", "email", "password_hash", "role", "password_version", "created_at", "last_signed_in_at"}


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


async def _register(c, email: str) -> int:
    r = await c.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    c.cookies.clear()
    return r.json()["user_id"]


async def test_sign_in_in_any_case_returns_200_and_writes_only_last_signed_in_at(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id = await _register(c, "Turing@Example.com")
        before = app_sql(migrated_db, IMMUTABLE, (user_id,))
        clock.advance(61)
        r = await c.post("/api/auth/login", json={"email": "  tURING@example.COM ", "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert session_cookie(r)
    assert r.json() == {"user_id": user_id, "email": "Turing@Example.com", "role": "customer"}
    assert app_sql(migrated_db, "SELECT last_signed_in_at FROM users WHERE id = %s", (user_id,)) == [(clock.now(),)]
    assert app_sql(migrated_db, IMMUTABLE, (user_id,)) == before
    assert app_sql(migrated_db, "SELECT count(*) FROM audit_log WHERE actor_user_id = %s", (user_id,)) == [(0,)]


async def test_unknown_address_and_wrong_password_are_identical_but_for_the_request_id(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id = await _register(c, "hopper@example.com")
        unknown = await c.post("/api/auth/login", json={"email": "nobody-here@example.com", "password": PASSWORD})
        wrong = await c.post("/api/auth/login", json={"email": "hopper@example.com", "password": "not the password"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.headers["content-type"] == wrong.headers["content-type"]
    assert unknown.json()["error"]["request_id"] != wrong.json()["error"]["request_id"]
    assert without_request_id(unknown.json()) == without_request_id(wrong.json())
    assert set(unknown.json()["error"]) == set(wrong.json()["error"])
    for r in (unknown, wrong):
        assert r.json()["error"]["code"] == "CREDENTIALS_INVALID"
        assert r.json()["error"]["message"] == MISMATCH
        assert session_cookie(r) is None
    assert app_sql(migrated_db, "SELECT last_signed_in_at FROM users WHERE id = %s", (user_id,)) == [(None,)]


@pytest.mark.parametrize("body", [{}, {"email": "a@example.com"}, {"password": PASSWORD}, {"email": "", "password": PASSWORD},
                                  {"email": "a@example.com", "password": ""}, {"email": "   ", "password": PASSWORD}])
async def test_a_missing_or_empty_field_is_422(migrated_db, clock, body):
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/login", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert r.json()["error"]["message"] == "Enter your email address and password."


async def test_a_ten_character_stored_password_still_signs_in(migrated_db, clock):
    insert_user(migrated_db, role="customer", email="legacy@example.com", password_hash=security.hash_password("tenchars10", 4))
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/login", json={"email": "legacy@example.com", "password": "tenchars10"})
    assert r.status_code == 200, r.text


async def test_nine_failures_lock_nothing_and_the_tenth_attempt_signs_in(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id = await _register(c, "lovelace@example.com")
        role_before = app_sql(migrated_db, "SELECT role FROM users WHERE id = %s", (user_id,))
        codes = [(await c.post("/api/auth/login", json={"email": "lovelace@example.com", "password": f"wrong {i} horse"})).status_code
                 for i in range(9)]
        tenth = await c.post("/api/auth/login", json={"email": "lovelace@example.com", "password": PASSWORD})
    assert codes == [401] * 9
    assert app_sql(migrated_db, "SELECT role FROM users WHERE id = %s", (user_id,)) == role_before
    cols = {r[0] for r in app_sql(migrated_db, "SELECT column_name FROM information_schema.columns "
                                               "WHERE table_schema = 'public' AND table_name = 'users'")}
    assert cols == SEVEN
    assert tenth.status_code == 200

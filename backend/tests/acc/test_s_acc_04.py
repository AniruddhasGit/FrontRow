"""S-ACC-04 - the session cookie, its revocation on a password change, and a public sign-out
(P-ACC-05, EP-ACC-02..04)."""

from __future__ import annotations

import os
import subprocess
import sys

import jwt
import pytest

from app.core.security import SESSION_COOKIE
from tests.acc._support import api, cookie_attributes, flush_redis, jwt_claims, session_cookie, settings_for
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR, app_sql, owner_sql

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
CLAIMS = ("sub", "role", "pv", "iat", "exp")


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


async def _signed_in(c, email: str) -> tuple[int, object]:
    await c.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    c.cookies.clear()
    r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["user_id"], r


@pytest.mark.parametrize("secure,base", [("false", "http://localhost:8080"), ("true", "https://frontrow.example.invalid")])
async def test_the_cookie_attributes_with_secure_from_configuration(migrated_db, clock, secure, base):
    async with api(settings_for(migrated_db, COOKIE_SECURE=secure, PUBLIC_BASE_URL=base), clock) as c:
        _, r = await _signed_in(c, f"cookie-{secure}@example.com")
    [header] = [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE + "=")]
    attrs = cookie_attributes(header)
    assert session_cookie(r).count(".") == 2  # a JWT
    assert set(attrs) == {"httponly", "samesite", "path", "max-age"} | ({"secure"} if secure == "true" else set())
    assert attrs["samesite"].lower() == "lax"  # attribute values are case-insensitive (RFC 6265 5.2)
    assert (attrs["path"], attrs["max-age"]) == ("/", "43200")


@pytest.mark.parametrize("missing", ["COOKIE_SECURE", "JWT_SECRET"])
def test_the_process_refuses_to_start_without_the_variable_and_names_it_on_stderr(tmp_path, missing):
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({k: v for k, v in VALID_ENV.items() if k != missing})
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert missing in proc.stderr


async def test_the_token_carries_exactly_five_claims_and_no_email(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id, r = await _signed_in(c, "claims@example.com")
    claims = jwt_claims(session_cookie(r))
    assert set(claims) == set(CLAIMS)
    assert claims["sub"] == str(user_id)
    assert "claims@example.com" not in str(claims)


async def test_a_password_version_behind_the_row_is_refused(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id, _ = await _signed_in(c, "pv@example.com")
        assert (await c.get("/api/auth/me")).status_code == 200
        app_sql(migrated_db, "UPDATE users SET password_version = password_version + 1 WHERE id = %s", (user_id,))
        r = await c.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r.json()["error"]["message"] == "Your session has ended because the password was changed. Sign in to continue."


async def test_a_removed_user_row_is_refused(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id, _ = await _signed_in(c, "gone@example.com")
        owner_sql(migrated_db, "DELETE FROM users WHERE id = %s", (user_id,))
        r = await c.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"] == {**r.json()["error"], "code": "AUTH_REQUIRED", "message": "Sign in to continue."}


@pytest.mark.parametrize("dropped", CLAIMS)
async def test_a_token_missing_one_claim_is_refused_not_defaulted(migrated_db, clock, dropped):
    settings = settings_for(migrated_db)
    async with api(settings, clock) as c:
        _, r = await _signed_in(c, f"drop-{dropped}@example.com")
        claims = {k: v for k, v in jwt_claims(session_cookie(r)).items() if k != dropped}
        forged = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")
        c.cookies.clear()
        c.cookies.set(SESSION_COOKIE, forged)
        me = await c.get("/api/auth/me")
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_a_role_changed_in_the_database_applies_on_the_next_request(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        user_id, _ = await _signed_in(c, "promoted@example.com")
        assert (await c.get("/api/auth/me")).json()["role"] == "customer"
        app_sql(migrated_db, "UPDATE users SET role = 'manager' WHERE id = %s", (user_id,))
        assert (await c.get("/api/auth/me")).json()["role"] == "manager"


async def test_sign_out_is_204_with_a_matching_clearing_cookie_in_every_state(migrated_db, clock):
    settings = settings_for(migrated_db)
    async with api(settings, clock) as c:
        _, signed = await _signed_in(c, "leaver@example.com")
        issued = cookie_attributes(next(h for h in signed.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE + "=")))
        responses = [await c.post("/api/auth/logout")]
        c.cookies.clear()
        responses.append(await c.post("/api/auth/logout"))  # no cookie at all
        expired = jwt.encode({"sub": "1", "role": "customer", "pv": 1, "iat": 0, "exp": 1}, settings.JWT_SECRET, algorithm="HS256")
        for value in (expired, "not.a.jwt"):
            c.cookies.clear()
            c.cookies.set(SESSION_COOKIE, value)
            responses.append(await c.post("/api/auth/logout"))
        responses.append(await c.post("/api/auth/logout"))  # a second consecutive call
    for r in responses:
        assert r.status_code == 204, r.text
        [header] = r.headers.get_list("set-cookie")
        assert header.startswith(f"{SESSION_COOKIE}=;")
        attrs = cookie_attributes(header)
        assert attrs["max-age"] == "0"
        assert {k: v for k, v in attrs.items() if k != "max-age"} == {k: v for k, v in issued.items() if k != "max-age"}


async def test_no_session_table_exists(migrated_db):
    assert app_sql(migrated_db, "SELECT to_regclass('session')") == [(None,)]

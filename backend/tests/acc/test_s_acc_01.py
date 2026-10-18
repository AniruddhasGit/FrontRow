"""S-ACC-01 - create the users table and register an account in one request (P-ACC-01, EP-ACC-01).

Every clause of the acceptance criterion, through POST /api/auth/register on the real app against a
migrated throwaway database and the compose Redis.
"""

from __future__ import annotations

import asyncio
import io
import logging

import pytest

from app.core.logging import configure_logging
from tests.acc._support import api, flush_redis, session_cookie, settings_for
from tests.dbkit import app_sql

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
DUPLICATE_MESSAGE = ("An account already exists for that email address. Sign in instead, or reset the password "
                     "if you have forgotten it.")


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


async def test_register_returns_201_sets_the_session_and_stores_one_customer_row(migrated_db, clock, capsys):
    stream = io.StringIO()
    configure_logging(level="DEBUG", service="api", instance_id="test0001", now=clock.now, stream=stream)
    try:
        async with api(settings_for(migrated_db, LOG_LEVEL="DEBUG"), clock) as c:
            assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
            r = await c.post("/api/auth/register", json={"email": " Ada@Example.com ", "password": PASSWORD})
    finally:
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)
    captured = stream.getvalue() + capsys.readouterr().out

    assert r.status_code == 201, r.text
    assert session_cookie(r)
    body = r.json()
    assert set(body) == {"user_id", "email", "role"}
    assert body["email"] == "Ada@Example.com" and body["role"] == "customer" and isinstance(body["user_id"], int)

    rows = app_sql(migrated_db, "SELECT email, role, password_version, last_signed_in_at, password_hash FROM users "
                                "WHERE lower(email) = 'ada@example.com'")
    assert len(rows) == 1
    email, role, version, last, password_hash = rows[0]
    assert (email, role, version, last) == ("Ada@Example.com", "customer", 1, None)
    assert password_hash != PASSWORD

    assert "/api/auth/register" in captured  # the capture covered the request (its completion line)
    assert PASSWORD not in r.text
    assert PASSWORD not in captured
    (row_text,) = app_sql(migrated_db, "SELECT users::text FROM users WHERE lower(email) = 'ada@example.com'")[0]
    assert PASSWORD not in row_text


async def test_the_users_table_has_exactly_the_seven_columns(migrated_db):
    cols = {r[0] for r in app_sql(migrated_db, "SELECT column_name FROM information_schema.columns "
                                               "WHERE table_schema = 'public' AND table_name = 'users'")}
    assert cols == {"id", "email", "password_hash", "role", "password_version", "created_at", "last_signed_in_at"}


async def test_a_second_registration_in_another_case_is_409(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        first = await c.post("/api/auth/register", json={"email": "Grace@Example.com", "password": PASSWORD})
        second = await c.post("/api/auth/register", json={"email": "GRACE@example.com", "password": PASSWORD})
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert second.json()["error"]["message"] == DUPLICATE_MESSAGE


async def test_twenty_simultaneous_identical_registrations_make_one_account(migrated_db, clock):
    # P-XCT-07: a larger configured bucket, never a disabled control - every request is still counted.
    async with api(settings_for(migrated_db, RATE_LIMIT_REGISTER_IP_PER_HOUR="25"), clock) as c:
        body = {"email": "Lin@Example.com", "password": PASSWORD}
        responses = await asyncio.gather(*(c.post("/api/auth/register", json=body) for _ in range(20)))
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] + [409] * 19, [(r.status_code, r.text) for r in responses]
    assert all(r.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED" for r in responses if r.status_code == 409)
    assert not any(r.status_code >= 500 for r in responses)
    assert not any(r.status_code != 201 and r.json()["error"]["code"] == "RATE_LIMITED" for r in responses)
    assert app_sql(migrated_db, "SELECT count(*) FROM users WHERE lower(email) = 'lin@example.com'") == [(1,)]


async def test_the_bucket_is_still_counting_during_the_larger_bucket_run(migrated_db, clock):
    """Proves the 20-way run above had a live limiter: the 26th request in the hour is refused."""
    async with api(settings_for(migrated_db, RATE_LIMIT_REGISTER_IP_PER_HOUR="25"), clock) as c:
        body = {"email": "Count@Example.com", "password": PASSWORD}
        codes = [(await c.post("/api/auth/register", json=body)).status_code for _ in range(26)]
    assert codes[25] == 429


async def test_role_is_never_read_from_the_request_body(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "mallory@example.com", "password": PASSWORD, "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "customer"
    assert app_sql(migrated_db, "SELECT role FROM users WHERE lower(email) = 'mallory@example.com'") == [("customer",)]

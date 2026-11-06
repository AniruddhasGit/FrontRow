"""S-ACC-08 - complete a password reset once, and only once, ending every existing session (P-ACC-08, EP-ACC-06).

Tokens are planted directly (the hash of a known 43-character value) so each test names its own; the request half is
S-ACC-07. Time is injected (SetClock). The 50-way race runs the real app on one event loop, with bcrypt in its thread
pool, so the 50 requests interleave at every await - the conditional UPDATE is the only thing that decides.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import socket
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.core import security
from app.core.logging import configure_logging
from tests.acc._support import SetClock, api, flush_redis, session_cookie, settings_for
from tests.dbkit import app_sql, insert_user, owner_sql

pytestmark = pytest.mark.anyio

T10 = datetime(2026, 8, 14, 10, 0, 0, tzinfo=timezone.utc)
OLD = "the old password value"
NEW = "a brand new password"
USED = "That reset link has already been used. Request a new one."


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


@pytest.fixture
def at10():
    c = SetClock()
    c.set(T10)
    return c


def _token(n: int) -> str:
    return (f"tok{n:04d}" + "A" * 43)[:43]


def _plant(db, user: int, token: str, *, created: datetime = T10, used: bool = False) -> int:
    return owner_sql(db, "INSERT INTO password_reset_token (user_id, token_sha256, expires_at, used_at, created_at) "
                         "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                     (user, hashlib.sha256(token.encode()).hexdigest(), created + timedelta(seconds=1800),
                      created if used else None, created))[0][0]


def _user(db, email: str) -> int:
    return insert_user(db, role="customer", email=email, password_hash=security.hash_password(OLD, 4))


def _row(db, user: int):
    return app_sql(db, "SELECT password_hash, password_version, last_signed_in_at FROM users WHERE id = %s", (user,))[0]


async def test_a_live_token_changes_the_password_in_one_transaction_and_ends_the_old_session(migrated_db, at10):
    user = _user(migrated_db, "reset@example.com")
    token = _token(1)
    token_id = _plant(migrated_db, user, token)
    async with api(settings_for(migrated_db), at10) as c:
        signed = await c.post("/api/auth/login", json={"email": "reset@example.com", "password": OLD})
        old_cookie = session_cookie(signed)
        c.cookies.clear()
        at10.advance(60)
        r = await c.post("/api/auth/password-reset/confirm", json={"token": token, "password": NEW})
        new_cookie = session_cookie(r)
        c.cookies.clear()
        old_me = await c.get("/api/auth/me", cookies={"fr_session": old_cookie})
        new_me = await c.get("/api/auth/me", cookies={"fr_session": new_cookie})
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"user_id", "email", "role"} and new_cookie and new_cookie != old_cookie
    password_hash, version, last = _row(migrated_db, user)
    assert version == 2 and security.verify_password(NEW, password_hash, 4)
    assert last == T10 + timedelta(seconds=60)
    assert app_sql(migrated_db, "SELECT used_at FROM password_reset_token WHERE id = %s", (token_id,)) == [(last,)]
    assert (old_me.status_code, old_me.json()["error"]["code"]) == (401, "AUTH_REQUIRED")
    assert new_me.status_code == 200


async def test_a_rolled_back_reset_leaves_the_token_unused_and_the_password_unchanged(migrated_db, at10, monkeypatch):
    from app.domain import accounts

    user = _user(migrated_db, "rollback8@example.com")
    token = _token(2)
    token_id = _plant(migrated_db, user, token)
    before = _row(migrated_db, user)
    real_update = accounts.update

    def failing_update(table):
        stmt = real_update(table)
        if table is accounts.users:
            raise RuntimeError("forced failure after the token UPDATE, inside the transaction")
        return stmt

    monkeypatch.setattr(accounts, "update", failing_update)
    async with api(settings_for(migrated_db), at10) as c:
        r = await c.post("/api/auth/password-reset/confirm", json={"token": token, "password": NEW})
    assert r.status_code == 500
    assert app_sql(migrated_db, "SELECT used_at FROM password_reset_token WHERE id = %s", (token_id,)) == [(None,)]
    assert _row(migrated_db, user) == before and before[1] == 1


async def test_fifty_simultaneous_submissions_of_one_token_make_one_success(migrated_db, at10):
    user = _user(migrated_db, "race@example.com")
    token = _token(3)
    _plant(migrated_db, user, token)
    # Configured above 50 for this run so the confirm bucket refuses none of them (P-XCT-07: sizing is not disabling).
    # The pool and the command timeout are raised so 50 requests on one loop queue rather than time out: the race is
    # decided by the conditional UPDATE, and a 503 from an exhausted test pool would hide that.
    settings = settings_for(migrated_db, RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR="100", DB_POOL_SIZE="50",
                            REDIS_COMMAND_TIMEOUT_MS="10000", BCRYPT_HASH_TIMEOUT_MS="60000")
    async with api(settings, at10) as c:
        rs = await asyncio.gather(*[c.post("/api/auth/password-reset/confirm", json={"token": token, "password": NEW})
                                    for _ in range(50)])
    codes = sorted(r.status_code for r in rs)
    assert codes == [200] + [400] * 49
    refused = [r.json()["error"] for r in rs if r.status_code == 400]
    assert all((e["code"], e["message"]) == ("RESET_TOKEN_INVALID", USED) for e in refused)
    assert not [r for r in rs if r.status_code != 200 and r.json()["error"]["code"] == "RATE_LIMITED"]
    assert app_sql(migrated_db, "SELECT password_version FROM users WHERE id = %s", (user,)) == [(2,)]


async def test_unknown_and_expired_tokens_get_their_own_sentences(migrated_db, at10):
    user = _user(migrated_db, "expired@example.com")
    live = _token(4)
    _plant(migrated_db, user, live)
    async with api(settings_for(migrated_db), at10) as c:
        unknown = await c.post("/api/auth/password-reset/confirm", json={"token": _token(9999), "password": NEW})
        at10.advance(1801)  # 10:30:01, past expires_at 10:30:00
        expired = await c.post("/api/auth/password-reset/confirm", json={"token": live, "password": NEW})
    assert (unknown.status_code, unknown.json()["error"]["message"]) == (400, "That reset link is not valid. Request a new one.")
    assert (expired.status_code, expired.json()["error"]["message"]) == (400, "That reset link has expired. Request a new one.")
    assert {unknown.json()["error"]["code"], expired.json()["error"]["code"]} == {"RESET_TOKEN_INVALID"}


async def test_a_wrong_length_token_is_422_and_issues_no_statement(migrated_db, at10):
    statements: list[str] = []
    async with api(settings_for(migrated_db), at10) as c:
        engine = c.application.state.db_engine.sync_engine
        listener = lambda conn, cursor, stmt, params, context, many: statements.append(stmt)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            rs = [await c.post("/api/auth/password-reset/confirm", json={"token": "A" * n, "password": NEW}) for n in (42, 44, 0)]
            rs.append(await c.post("/api/auth/password-reset/confirm", json={"password": NEW}))
        finally:
            event.remove(engine, "before_cursor_execute", listener)
    assert [r.status_code for r in rs] == [422] * 4
    assert {r.json()["error"]["code"] for r in rs} == {"VALIDATION_FAILED"}
    assert statements == []


async def test_a_wrong_length_token_is_422_not_503_with_the_database_port_closed(migrated_db, at10):
    with socket.socket() as s:  # a port nothing listens on: bind, read the number, close
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings = settings_for(migrated_db, DATABASE_URL=f"postgresql://frontrow_app:x@127.0.0.1:{port}/nothing")
    async with api(settings, at10) as c:
        r = await c.post("/api/auth/password-reset/confirm", json={"token": "A" * 42, "password": NEW})
    assert r.status_code == 422, r.text


async def test_the_body_schema_is_exactly_token_and_password_and_an_old_password_is_ignored(migrated_db, at10):
    user = _user(migrated_db, "oldpw@example.com")
    token = _token(5)
    _plant(migrated_db, user, token)
    before = app_sql(migrated_db, "SELECT count(*) FROM outbox_message")
    async with api(settings_for(migrated_db), at10) as c:
        schema = c.application.openapi()
        r = await c.post("/api/auth/password-reset/confirm",
                         json={"token": token, "password": NEW, "old_password": "certainly not the old one"})
    ref = schema["paths"]["/api/auth/password-reset/confirm"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert set(schema["components"]["schemas"][ref.rsplit("/", 1)[1]]["properties"]) == {"token", "password"}
    assert r.status_code == 200
    assert app_sql(migrated_db, "SELECT count(*) FROM outbox_message") == before  # no confirmation email


async def test_the_token_appears_in_no_debug_line(migrated_db, at10):
    user = _user(migrated_db, "debug8@example.com")
    token = _token(6)
    _plant(migrated_db, user, token)
    stream = io.StringIO()
    configure_logging(level="DEBUG", service="api", instance_id="test0001", now=at10.now, stream=stream)
    try:
        async with api(settings_for(migrated_db, LOG_LEVEL="DEBUG"), at10) as c:
            r = await c.post("/api/auth/password-reset/confirm", json={"token": token, "password": NEW})
    finally:
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)
    captured = stream.getvalue()
    assert r.status_code == 200
    assert "/api/auth/password-reset/confirm" in captured
    assert token not in captured

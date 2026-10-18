"""S-XCT-06 - every privileged change and its audit row are written in one transaction.

Exercises app/core/audit.py against a migrated database, connected as frontrow_app, with the change
written in the same `async with conn.begin()` block an admin handler uses. The request id is bound by
the same context the middleware uses and is generated, never a literal. The commit, rollback and no-row clauses
are ALSO proved through the real request path, EP-ADM-11 (PATCH /api/admin/showtimes/{id}), with the request id
read from the response at assertion time (the tests prefixed test_http_).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, update

from app.api.deps import CurrentUser
from app.core import audit as audit_module
from app.core.audit import write_audit
from app.core.logging import bind_request_id, new_request_id
from app.models import showtime
from tests.dbkit import app_sql, insert_showtime, insert_user, owner_sql

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 14, 14, 7, 11, tzinfo=timezone.utc)  # the worked example's instant, injected


@pytest.fixture(scope="module")
def seeded(migrated_db):
    insert_user(migrated_db, role="admin", user_id=17, email="admin17@example.invalid")
    insert_showtime(migrated_db, showtime_id=41, base_price_paise=25000)
    return migrated_db


@pytest.fixture
async def engine(seeded):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db import async_url

    eng = create_async_engine(async_url(seeded.app_url))
    yield eng
    await eng.dispose()


def _reset_price(db):
    owner_sql(db, "UPDATE showtime SET base_price_paise = 25000 WHERE id = 41")


ADMIN = CurrentUser(id=17, email="admin17@example.invalid", role="admin", password_version=1)


async def _change_price(conn, new_price: int) -> None:
    await conn.execute(update(showtime).where(showtime.c.id == 41).values(base_price_paise=new_price))


async def test_the_change_and_its_audit_row_commit_together_with_every_field(seeded, engine):
    _reset_price(seeded)
    request_id = new_request_id()
    with bind_request_id(request_id):
        async with engine.connect() as conn, conn.begin():
            await _change_price(conn, 28000)
            await write_audit(conn, actor=ADMIN, action="showtime.base_price_changed", entity_type="showtime", entity_id=41,
                              before={"base_price_paise": 25000}, after={"base_price_paise": 28000}, occurred_at=NOW)
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)
    rows = app_sql(seeded, "SELECT actor_user_id, actor_role, action, entity_type, entity_id, before, after, request_id, occurred_at "
                           "FROM audit_log WHERE request_id = %s", (request_id,))
    assert rows == [(17, "admin", "showtime.base_price_changed", "showtime", 41, {"base_price_paise": 25000},
                     {"base_price_paise": 28000}, request_id, NOW)]
    assert app_sql(seeded, "SELECT base_price_paise FROM showtime WHERE id = 41") == [(28000,)]


async def test_a_failing_audit_insert_rolls_the_change_back(seeded, engine, monkeypatch):
    _reset_price(seeded)
    (before_count,) = app_sql(seeded, "SELECT count(*) FROM audit_log")[0]

    async def boom(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(audit_module, "write_audit", boom)
    with pytest.raises(RuntimeError):
        async with engine.connect() as conn, conn.begin():
            await _change_price(conn, 28000)
            await audit_module.write_audit(conn, actor=ADMIN, action="showtime.base_price_changed", entity_type="showtime",
                                           entity_id=41, before={"base_price_paise": 25000}, after={"base_price_paise": 28000},
                                           occurred_at=NOW)
    assert app_sql(seeded, "SELECT base_price_paise FROM showtime WHERE id = 41") == [(25000,)]
    assert app_sql(seeded, "SELECT count(*) FROM audit_log") == [(before_count,)]


async def test_a_failing_change_leaves_no_audit_row(seeded, engine):
    owner_sql(seeded, "DELETE FROM audit_log WHERE entity_id = 41")  # owner-only cleanup between tests
    _reset_price(seeded)

    async def failing_update(conn, new_price):
        raise RuntimeError("the showtime UPDATE failed")

    with pytest.raises(RuntimeError):
        async with engine.connect() as conn, conn.begin():
            await failing_update(conn, 28000)
            await write_audit(conn, actor=ADMIN, action="showtime.base_price_changed", entity_type="showtime", entity_id=41,
                              before={"base_price_paise": 25000}, after={"base_price_paise": 28000}, occurred_at=NOW)
    assert app_sql(seeded, "SELECT count(*) FROM audit_log WHERE entity_id = 41 AND action = 'showtime.base_price_changed'") == [(0,)]


def test_actor_user_id_is_not_null_and_a_foreign_key_to_users(seeded):
    assert app_sql(seeded, "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
                           "AND table_name='audit_log' AND column_name='actor_user_id'") == [("NO",)]
    fks = owner_sql(seeded, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='audit_log'::regclass AND contype='f'")
    assert len(fks) == 1
    assert fks[0][1].startswith("FOREIGN KEY (actor_user_id) REFERENCES users(id)")


async def test_actor_role_is_copied_at_write_time_not_joined_at_read_time(seeded, engine):
    user_id = insert_user(seeded, role="admin")
    actor = CurrentUser(id=user_id, email="x@example.invalid", role="admin", password_version=1)
    request_id = new_request_id()
    with bind_request_id(request_id):
        async with engine.connect() as conn, conn.begin():
            await write_audit(conn, actor=actor, action="showtime.updated", entity_type="showtime", entity_id=41,
                              before={"starts_at": "a"}, after={"starts_at": "b"}, occurred_at=NOW)
    owner_sql(seeded, "UPDATE users SET role = 'manager' WHERE id = %s", (user_id,))
    assert app_sql(seeded, "SELECT actor_role FROM audit_log WHERE request_id = %s", (request_id,)) == [("admin",)]


async def test_before_and_after_carry_only_the_changed_field_and_before_is_null_on_creation(seeded, engine):
    change_id, create_id = new_request_id(), new_request_id()
    async with engine.connect() as conn:
        with bind_request_id(change_id):
            async with conn.begin():
                await write_audit(conn, actor=ADMIN, action="showtime.base_price_changed", entity_type="showtime", entity_id=41,
                                  before={"base_price_paise": 25000}, after={"base_price_paise": 28000}, occurred_at=NOW)
        with bind_request_id(create_id):
            async with conn.begin():
                await write_audit(conn, actor=ADMIN, action="showtime.created", entity_type="showtime", entity_id=41,
                                  before=None, after={"base_price_paise": 25000}, occurred_at=NOW)
    assert app_sql(seeded, "SELECT (SELECT count(*) FROM jsonb_object_keys(before)), (SELECT count(*) FROM jsonb_object_keys(after)) "
                           "FROM audit_log WHERE request_id = %s", (change_id,)) == [(1, 1)]
    assert app_sql(seeded, "SELECT before IS NULL FROM audit_log WHERE request_id = %s", (create_id,)) == [(True,)]


async def test_occurred_at_is_timestamptz_and_the_bound_value_is_aware_utc(seeded, engine):
    assert app_sql(seeded, "SELECT data_type FROM information_schema.columns WHERE table_schema = 'public' "
                           "AND table_name='audit_log' AND column_name='occurred_at'") == [("timestamp with time zone",)]
    captured = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO AUDIT_LOG"):
            captured.append(parameters)

    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        async with engine.connect() as conn, conn.begin():
            await write_audit(conn, actor=ADMIN, action="showtime.updated", entity_type="showtime", entity_id=41,
                              before={"ends_at": "a"}, after={"ends_at": "b"}, occurred_at=NOW)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert len(captured) == 1
    bound = [v for v in (captured[0].values() if isinstance(captured[0], dict) else captured[0]) if isinstance(v, datetime)]
    assert len(bound) == 1
    assert bound[0].tzinfo is not None and bound[0].utcoffset() == timedelta(0)


@pytest.mark.parametrize("bad", [datetime(2026, 8, 14, 14, 7, 11), datetime(2026, 8, 14, 19, 37, 11, tzinfo=timezone(timedelta(hours=5, minutes=30)))])
async def test_a_naive_or_non_utc_instant_is_refused_before_anything_is_written(seeded, engine, bad):
    with pytest.raises(ValueError):
        async with engine.connect() as conn, conn.begin():
            await write_audit(conn, actor=ADMIN, action="showtime.updated", entity_type="showtime", entity_id=41,
                              before={"a": 1}, after={"a": 2}, occurred_at=bad)


# ---- the same clauses through the real request path, EP-ADM-11 PATCH /api/admin/showtimes/{id} ----------------


@pytest.fixture
def admin_http(seeded, clock):
    from fastapi.testclient import TestClient

    from app.core.security import SESSION_COOKIE, issue_session_token
    from app.main import create_app
    from tests.dbkit import app_settings
    from tests.test_health import ok_probe

    owner_sql(seeded, "UPDATE showtime SET base_price_paise = 25000, version = 1 WHERE id = 41")
    application = create_app(app_settings(seeded), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(application, raise_server_exceptions=False) as c:
        c.cookies.set(SESSION_COOKIE, issue_session_token(user_id=17, role="admin", password_version=1, now=clock.now(),
                                                          settings=app_settings(seeded)))
        yield c


def _rid(r) -> str:
    rid = r.json()["error"]["request_id"] if r.status_code >= 400 else r.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{8}", rid) and rid == r.headers["x-request-id"]
    return rid


def test_http_the_price_change_and_its_audit_row_commit_together(seeded, admin_http):
    r = admin_http.patch("/api/admin/showtimes/41", json={"version": 1, "base_price_paise": 28000})
    assert r.status_code == 200, r.text
    rid = _rid(r)
    assert app_sql(seeded, "SELECT actor_user_id, actor_role, action, entity_type, entity_id, before, after FROM audit_log "
                           "WHERE request_id = %s", (rid,)) == [
        (17, "admin", "showtime.base_price_changed", "showtime", 41, {"base_price_paise": 25000}, {"base_price_paise": 28000})]
    assert app_sql(seeded, "SELECT base_price_paise FROM showtime WHERE id = 41") == [(28000,)]


def test_http_a_failing_audit_insert_rolls_the_price_back(seeded, admin_http, monkeypatch):
    from app.domain.admin import common

    (before_count,) = app_sql(seeded, "SELECT count(*) FROM audit_log")[0]

    async def boom(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(common, "write_audit", boom)
    r = admin_http.patch("/api/admin/showtimes/41", json={"version": 1, "base_price_paise": 28000})
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
    _rid(r)
    assert app_sql(seeded, "SELECT base_price_paise FROM showtime WHERE id = 41") == [(25000,)]
    assert app_sql(seeded, "SELECT count(*) FROM audit_log") == [(before_count,)]


def test_http_a_failing_update_leaves_no_audit_row(seeded, admin_http, monkeypatch):
    from app.domain.admin import showtimes as showtimes_domain

    owner_sql(seeded, "DELETE FROM audit_log WHERE entity_id = 41")  # owner-only cleanup between tests

    def failing_update(*args, **kwargs):
        raise RuntimeError("the showtime UPDATE failed")

    monkeypatch.setattr(showtimes_domain, "update", failing_update)
    r = admin_http.patch("/api/admin/showtimes/41", json={"version": 1, "base_price_paise": 28000})
    assert r.status_code == 500
    assert app_sql(seeded, "SELECT count(*) FROM audit_log WHERE entity_id = 41 AND action = 'showtime.base_price_changed'") == [(0,)]
    assert app_sql(seeded, "SELECT base_price_paise FROM showtime WHERE id = 41") == [(25000,)]

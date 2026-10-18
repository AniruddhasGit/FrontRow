"""S-ACC-06 - no verification gate and no address-change endpoint (P-ACC-04, EP-ACC-01).

Two clauses of this criterion name endpoints this build does not have yet, and the assertions for
them are written as the criterion states them, so they stay RED until those endpoints exist:
EP-ACC-05/06 (password reset, Phase 5 per SRC-004 JC-R6-02). EP-ADM-23/24 (the admin lane's manager
endpoints) are driven here as the criterion lists them. Nothing here is skipped.

The criterion says "a SQLAlchemy before_update event listener registered on the users mapper". This
codebase uses SQLAlchemy Core (app/models is a Core Table mirror) and has no mapper, so the listener
is the Core equivalent: a before_execute hook on the app's engine that records the SET columns of
every UPDATE statement issued against the users table. [JUDGMENT CALL]
"""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.sql.dml import Update

from app.core import security
from app.models import users
from tests.acc._support import api, flush_redis, settings_for
from tests.dbkit import app_sql, insert_booking, insert_showtime, insert_user
from tests.xct._support import rg

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
GATE_WORDS = ("verify", "verified", "unverified", "verification", "confirm your email", "not confirmed")


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


async def test_a_new_account_reaches_me_at_once_with_exactly_three_keys(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "instant@example.com", "password": PASSWORD})
        me = await c.get("/api/auth/me")
    assert r.status_code == 201
    assert me.status_code == 200
    assert set(me.json()) == {"user_id", "email", "role"} and me.json()["role"] == "customer"


async def test_registration_enqueues_nothing(migrated_db, clock):
    before = app_sql(migrated_db, "SELECT count(*) FROM outbox_message")
    async with api(settings_for(migrated_db), clock) as c:
        assert (await c.post("/api/auth/register", json={"email": "quiet@example.com", "password": PASSWORD})).status_code == 201
    assert app_sql(migrated_db, "SELECT count(*) FROM outbox_message") == before


async def test_no_response_body_speaks_of_verification(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        bodies = [await c.post("/api/auth/register", json={"email": "words@example.com", "password": PASSWORD}),
                  await c.get("/api/auth/me"),
                  await c.post("/api/auth/register", json={"email": "words@example.com", "password": PASSWORD})]
        c.cookies.clear()
        bodies.append(await c.post("/api/auth/login", json={"email": "words@example.com", "password": "wrong horse battery"}))
        # The fifth body of the criterion, the 202 from EP-ACC-05, is asserted once that endpoint exists.
        bodies.append(await c.post("/api/auth/password-reset/request", json={"email": "words@example.com"}))
    assert [r.status_code for r in bodies] == [201, 200, 409, 401, 202]
    for r in bodies:
        assert not [w for w in GATE_WORDS if w in r.text.lower()], r.text
    pattern = r"(?i)unverified|not verified|verify your email|verify your address|email_verified"
    assert rg(pattern, "backend/app", "frontend/src") == []


async def test_a_second_account_does_not_move_the_first_booking(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        first = (await c.post("/api/auth/register", json={"email": "typo@exmaple.com", "password": PASSWORD})).json()["user_id"]
        booking = insert_booking(migrated_db, user_id=first, showtime=insert_showtime(migrated_db), price_paise=25000,
                                 reference="ACDEFHJK")
        c.cookies.clear()
        second = await c.post("/api/auth/register", json={"email": "typo@example.com", "password": PASSWORD})
    assert second.status_code == 201 and second.json()["user_id"] != first
    assert app_sql(migrated_db, "SELECT user_id FROM booking WHERE reference = 'ACDEFHJK'") == [(first,)]
    assert booking


async def test_exactly_four_operations_take_an_email_and_none_is_a_patch_or_put(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        schema = c.application.openapi()
    takers = set()
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            ref = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
            props = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]["properties"] if ref else {}
            if "email" in props:
                takers.add((method.upper(), path))
    assert not [t for t in takers if t[0] in ("PATCH", "PUT")]
    assert takers == {("POST", "/api/auth/register"), ("POST", "/api/auth/login"),
                      ("POST", "/api/auth/password-reset/request"), ("POST", "/api/admin/managers")}


async def test_users_email_is_never_in_an_update(migrated_db, clock):
    changed: set[str] = set()
    async with api(settings_for(migrated_db), clock) as c:
        engine = c.application.state.db_engine.sync_engine

        def record(conn, clauseelement, multiparams, params, execution_options):
            if isinstance(clauseelement, Update) and clauseelement.table is users:
                values = clauseelement._values or {}
                changed.update(getattr(k, "key", str(k)) for k in values)
                for p in (params or {}, *(multiparams or ())):
                    if isinstance(p, dict):
                        changed.update(p)

        event.listen(engine, "before_execute", record)
        try:
            await c.post("/api/auth/register", json={"email": "mapper@example.com", "password": PASSWORD})
            c.cookies.clear()
            await c.post("/api/auth/login", json={"email": "mapper@example.com", "password": PASSWORD})
            await c.post("/api/auth/logout")
            insert_user(migrated_db, role="admin", email="admin-06@example.com",
                        password_hash=security.hash_password(PASSWORD, 4))
            assert (await c.post("/api/auth/login", json={"email": "admin-06@example.com", "password": PASSWORD})).status_code == 200
            screen = insert_showtime(migrated_db)["screen_id"]
            created = await c.post("/api/admin/managers", json={"email": "manager-06@example.com", "screen_ids": [screen]})
            assert created.status_code == 201, created.text
            manager_id = app_sql(migrated_db, "SELECT id FROM users WHERE email = 'manager-06@example.com'")[0][0]
            put = await c.put(f"/api/admin/managers/{manager_id}/screens", json={"screen_ids": [screen]})
            assert put.status_code == 200, put.text
            # Phase 5 adds password-reset request and confirm here (EP-ACC-05/06, SRC-004 JC-R6-02). Until
            # they exist nothing writes password_hash or password_version and this assertion stays RED.
        finally:
            event.remove(engine, "before_execute", record)
    assert "email" not in changed
    assert changed == {"last_signed_in_at", "password_hash", "password_version"}

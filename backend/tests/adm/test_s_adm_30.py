"""S-ADM-30 - grant and remove admin access by email (SRC-008 ROLE-1 and its ADDENDUM; EP-ADM-30..32).

Every clause of the criterion, through the real app (httpx on the test's loop) against a migrated throwaway database
and the compose Redis. "After a fresh seed the list holds 0 rows" is held by S-XCT-45's table-count test, which reads
admin_grant rows 0 from docs/06 DataModel/seed/expected_summary.json; here the seeded admin's address is refused.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.security import SESSION_COOKIE, hash_password, issue_session_token
from tests.acc._support import api, flush_redis, settings_for
from tests.dbkit import insert_user, owner_sql

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
GRANTS = "/api/admin/admin-grants"


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


def _one(db, q, p=None):
    return owner_sql(db, q, p)[0][0]


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@example.invalid"


def _cookie(db, clock, user_id: int, role: str) -> dict:
    return {SESSION_COOKIE: issue_session_token(user_id=user_id, role=role, password_version=1, now=clock.now(),
                                                settings=settings_for(db))}


def _admin(db, clock, email: str | None = None) -> tuple[int, dict]:
    uid = insert_user(db, role="admin", email=email)
    return uid, _cookie(db, clock, uid, "admin")


def _account(db, role: str, email: str) -> int:
    return insert_user(db, role=role, email=email, password_hash=hash_password(PASSWORD, 4))


def _role(db, email: str) -> str:
    return _one(db, "SELECT role FROM users WHERE lower(email) = lower(%s)", (email,))


def _state(db) -> tuple:
    return (_one(db, "SELECT count(*) FROM admin_grant"), _one(db, "SELECT count(*) FROM audit_log"),
            owner_sql(db, "SELECT id, role FROM users ORDER BY id"))


async def test_the_list_is_admin_only_refused_at_the_router(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.get(GRANTS)
        assert (r.status_code, r.json()["error"]["code"]) == (401, "AUTH_REQUIRED")
        for role in ("customer", "manager"):
            r = await c.get(GRANTS, cookies=_cookie(migrated_db, clock, insert_user(migrated_db, role=role), role))
            assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN"), role
        _, admin = _admin(migrated_db, clock)
        r = await c.get(GRANTS, cookies=admin)
    assert r.status_code == 200 and isinstance(r.json()["items"], list)


async def test_add_and_remove_each_write_one_grant_change_and_one_audit_row(migrated_db, clock):
    admin_id, admin = _admin(migrated_db, clock)
    email = _email()
    async with api(settings_for(migrated_db), clock) as c:
        grants, audits = _one(migrated_db, "SELECT count(*) FROM admin_grant"), _one(migrated_db, "SELECT count(*) FROM audit_log")
        r = await c.post(GRANTS, json={"email": email}, cookies=admin)
        assert r.status_code == 201, r.text
        gid = r.json()["id"]
        assert r.json()["email"] == email and r.json()["granted_by"] == admin_id
        assert _one(migrated_db, "SELECT count(*) FROM admin_grant") == grants + 1
        assert owner_sql(migrated_db, "SELECT action, entity_type, entity_id, before, after, actor_user_id FROM audit_log "
                                      "WHERE id > (SELECT max(id) - 1 FROM audit_log)") == [
            ("admin_grant.created", "admin_grant", gid, None, {"email": email}, admin_id)]
        assert any(i["id"] == gid for i in (await c.get(GRANTS, cookies=admin)).json()["items"])
        r = await c.delete(f"{GRANTS}/{gid}", cookies=admin)
        assert r.status_code == 204, r.text
        assert _one(migrated_db, "SELECT count(*) FROM admin_grant WHERE id = %s", (gid,)) == 0
        assert _one(migrated_db, "SELECT count(*) FROM audit_log") == audits + 2
        assert owner_sql(migrated_db, "SELECT action, entity_id, before, actor_user_id FROM audit_log ORDER BY id DESC LIMIT 1") == [
            ("admin_grant.deleted", gid, {"email": email}, admin_id)]
        assert (await c.delete(f"{GRANTS}/{gid}", cookies=admin)).status_code == 404


async def test_a_failing_audit_insert_changes_nothing_on_add_or_remove(migrated_db, clock, monkeypatch):
    _, admin = _admin(migrated_db, clock)
    email = _email()
    _account(migrated_db, "admin", email)  # an admin account that holds its role through the grant below
    async with api(settings_for(migrated_db), clock) as c:
        gid = (await c.post(GRANTS, json={"email": _email()}, cookies=admin)).json()["id"]
        owner_sql(migrated_db, "UPDATE users SET role = 'customer' WHERE lower(email) = lower(%s)", (email,))
        held = (await c.post(GRANTS, json={"email": email}, cookies=admin)).json()["id"]
        owner_sql(migrated_db, "UPDATE users SET role = 'admin' WHERE lower(email) = lower(%s)", (email,))

        async def boom(*args, **kwargs):
            raise RuntimeError("audit insert failed")

        monkeypatch.setattr("app.domain.admin.admin_grants.audit", boom)
        before = _state(migrated_db)
        assert (await c.post(GRANTS, json={"email": _email()}, cookies=admin)).status_code == 500
        assert (await c.delete(f"{GRANTS}/{gid}", cookies=admin)).status_code == 500
        assert (await c.delete(f"{GRANTS}/{held}", cookies=admin)).status_code == 500  # would have demoted
        assert _state(migrated_db) == before
    assert _role(migrated_db, email) == "admin"


async def test_grants_are_trimmed_and_case_insensitive_and_register_makes_an_admin(migrated_db, clock):
    _, admin = _admin(migrated_db, clock)
    local = uuid.uuid4().hex[:8]
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post(GRANTS, json={"email": f" Ada{local}@Example.com "}, cookies=admin)
        assert r.status_code == 201 and r.json()["email"] == f"ada{local}@example.com"
        r = await c.post(GRANTS, json={"email": f"ADA{local}@example.com"}, cookies=admin)
        assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")
        assert _one(migrated_db, "SELECT count(*) FROM admin_grant WHERE email = %s", (f"ada{local}@example.com",)) == 1
        bad = await c.post(GRANTS, json={"email": "not an address"}, cookies=admin)
        assert (bad.status_code, bad.json()["error"]["details"]["field"]) == (422, "email")
        r = await c.post("/api/auth/register", json={"email": f"ada{local}@example.COM", "password": PASSWORD})
    assert r.status_code == 201 and r.json()["role"] == "admin"
    assert _role(migrated_db, f"ada{local}@example.com") == "admin"


async def test_an_existing_customer_becomes_admin_at_its_next_sign_in(migrated_db, clock):
    _, admin = _admin(migrated_db, clock)
    email = _email()
    _account(migrated_db, "customer", email)
    async with api(settings_for(migrated_db), clock) as c:
        assert (await c.post(GRANTS, json={"email": email.upper()}, cookies=admin)).status_code == 201
        assert _role(migrated_db, email) == "customer"  # not until it signs in
        r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert _role(migrated_db, email) == "admin"


async def test_a_granted_manager_becomes_admin_and_keeps_its_hall_assignments(migrated_db, clock):
    from tests.adm.kit import make_screen

    _, admin = _admin(migrated_db, clock)
    email = _email()
    manager = _account(migrated_db, "manager", email)
    owner_sql(migrated_db, "INSERT INTO manager_screen_assignment (user_id, screen_id) VALUES (%s, %s)",
              (manager, make_screen(migrated_db)))
    assigned = lambda: _one(migrated_db, "SELECT count(*) FROM manager_screen_assignment WHERE user_id = %s", (manager,))  # noqa: E731
    before = assigned()
    async with api(settings_for(migrated_db), clock) as c:
        assert (await c.post(GRANTS, json={"email": email}, cookies=admin)).status_code == 201
        r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert _role(migrated_db, email) == "admin" and assigned() == before == 1


async def test_a_role_in_the_body_is_still_ignored(migrated_db, clock):
    email = _email()
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/register", json={"email": email, "password": PASSWORD, "role": "admin"})
        assert r.status_code == 201 and r.json()["role"] == "customer"
        r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD, "role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "customer"
    assert _role(migrated_db, email) == "customer"


async def test_removing_the_email_of_an_admin_demotes_it_at_once(migrated_db, clock):
    _, admin = _admin(migrated_db, clock)
    email = _email()
    _account(migrated_db, "customer", email)
    async with api(settings_for(migrated_db), clock) as c:
        gid = (await c.post(GRANTS, json={"email": email}, cookies=admin)).json()["id"]
        r = await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        their = {SESSION_COOKIE: r.cookies[SESSION_COOKIE]}
        c.cookies.clear()
        assert (await c.get("/api/admin/movies", cookies=their)).status_code == 200
        assert (await c.delete(f"{GRANTS}/{gid}", cookies=admin)).status_code == 204
        assert _role(migrated_db, email) == "customer"
        r = await c.get("/api/admin/movies", cookies=their)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


async def test_an_admin_cannot_remove_their_own_email(migrated_db, clock):
    _, admin = _admin(migrated_db, clock)
    email = _email()
    me = _account(migrated_db, "customer", email)
    async with api(settings_for(migrated_db), clock) as c:
        gid = (await c.post(GRANTS, json={"email": email}, cookies=admin)).json()["id"]
        assert (await c.post("/api/auth/login", json={"email": email, "password": PASSWORD})).status_code == 200
        c.cookies.clear()
        before = _state(migrated_db)
        r = await c.delete(f"{GRANTS}/{gid}", cookies=_cookie(migrated_db, clock, me, "admin"))
    assert 400 <= r.status_code < 500 and r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert _state(migrated_db) == before and _role(migrated_db, email) == "admin"


async def test_the_seeded_admin_can_never_be_put_on_the_list(migrated_db, clock):
    seeded = f"admin-01@{uuid.uuid4().hex[:6]}.demo.frontrow.invalid"
    insert_user(migrated_db, role="admin", email=seeded)
    _, admin = _admin(migrated_db, clock)
    before = _state(migrated_db)
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post(GRANTS, json={"email": seeded.upper()}, cookies=admin)
    assert 400 <= r.status_code < 500 and r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert _state(migrated_db) == before


def test_the_four_roles_stay_four():
    from app.domain.accounts import Role

    assert sorted(member.value for member in Role) == ["admin", "customer", "guest", "manager"]

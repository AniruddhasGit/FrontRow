"""S-XCT-10 - authorisation applied once, on each router, as a dependency.

Covered: the routers registered in main.py carry their dependency at the router; no role check lives
outside api/deps.py; the role is read from the users row on every request; 401 / 403 bodies; a
manager's PATCH on the admin router is 403 before the body is validated; the reporting router mounts
no write route. The 401/403 clauses run through test routes mounted on routers built with the SAME
dependency objects the product routers carry (app.api.deps), because no product route exists yet.
NOT covered: the customer router (/api/me, /api/bookings, /api/holds) - no module exists for it.
"""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import admin, auth, auth_session, browse, manager
from app.api.deps import CurrentUser, current_user, require_admin, require_reporting
from app.core.security import SESSION_COOKIE, issue_session_token
from app.main import create_app
from tests.dbkit import BACKEND_DIR, app_settings, insert_user, owner_sql
from tests.test_health import ok_probe


def _calls(dependant) -> set:
    found = set()
    for d in dependant.dependencies:
        found.add(d.call)
        found |= _calls(d)
    return found


# ---- the route table ----------------------------------------------------------------------------------


def test_each_router_module_carries_exactly_its_one_authorisation_dependency():
    assert [d.dependency for d in admin.router.dependencies] == [require_admin]
    assert [d.dependency for d in manager.router.dependencies] == [require_reporting]
    assert [d.dependency for d in auth_session.router.dependencies] == [current_user]
    assert auth.router.dependencies == [] and browse.router.dependencies == []
    assert (admin.router.prefix, manager.router.prefix) == ("/api/admin", "/api/reports")


def test_the_application_holds_routes_never_routers_and_every_route_carries_its_prefix_dependency(valid_env):
    from app.core.config import load_settings

    application = create_app(load_settings(), probes=[ok_probe("postgres"), ok_probe("redis")])
    assert not any(isinstance(r, APIRouter) for r in application.routes)
    for route in (r for r in application.routes if isinstance(r, APIRoute)):
        calls = _calls(route.dependant)
        if route.path.startswith("/api/admin"):
            assert require_admin in calls, route.path
        if route.path.startswith("/api/reports"):
            assert require_reporting in calls, route.path
            assert not ({"POST", "PUT", "PATCH", "DELETE"} & route.methods), route.path


def test_no_role_check_lives_outside_deps_py():
    rx = re.compile(r"role\s*==|role\s*!=|current_user\.role|require_role|\.role\b")
    hits = [
        f"{p.relative_to(BACKEND_DIR)}:{i}: {line.strip()}"
        for p in (BACKEND_DIR / "app" / "api").rglob("*.py")
        if p.name != "deps.py"
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if rx.search(line)
    ]
    assert hits == []


# ---- behaviour through the dependency -------------------------------------------------------------------


class ShowtimePatch(BaseModel):
    base_price_paise: int


@pytest.fixture
def client(migrated_db, clock):
    application = create_app(app_settings(migrated_db), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    admin_like = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])

    @admin_like.get("/__test__/whoami")
    async def whoami(user: CurrentUser = Depends(current_user)) -> dict:
        return {"id": user.id, "role": user.role}

    @admin_like.patch("/showtimes/{showtime_id}")
    async def patch_showtime(showtime_id: int, body: ShowtimePatch) -> dict:
        return {"ok": True}

    application.include_router(admin_like)
    with TestClient(application) as c:
        c.app_clock = clock
        yield c


def _cookie(client, user_id: int, role: str, settings_db) -> dict:
    token = issue_session_token(user_id=user_id, role=role, password_version=1, now=client.app_clock.now(),
                                settings=app_settings(settings_db))
    return {SESSION_COOKIE: token}


def test_no_session_is_401_auth_required(client):
    r = client.get("/api/admin/__test__/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
    assert r.json()["error"]["message"] == "Sign in to continue."


def test_an_expired_session_is_401_signed_out(client, migrated_db):
    user = insert_user(migrated_db, role="admin")
    client.cookies.update(_cookie(client, user, "admin", migrated_db))
    client.app_clock.advance(43200)  # SESSION_TTL_SECONDS later, on the injected clock
    r = client.get("/api/admin/__test__/whoami")
    assert r.status_code == 401
    assert r.json()["error"] == {**r.json()["error"], "code": "AUTH_REQUIRED", "message": "You were signed out. Sign in again to continue."}


def test_a_token_that_does_not_verify_is_401_signed_out(client):
    client.cookies.set(SESSION_COOKIE, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.not-our-signature")
    r = client.get("/api/admin/__test__/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "You were signed out. Sign in again to continue."


def test_the_wrong_role_is_403_forbidden(client, migrated_db):
    user = insert_user(migrated_db, role="customer")
    client.cookies.update(_cookie(client, user, "customer", migrated_db))
    r = client.get("/api/admin/__test__/whoami")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_the_role_is_read_from_the_user_row_on_every_request_not_from_the_token(client, migrated_db):
    user = insert_user(migrated_db, role="admin")
    client.cookies.update(_cookie(client, user, "admin", migrated_db))  # the token says admin, and keeps saying it
    assert client.get("/api/admin/__test__/whoami").status_code == 200
    owner_sql(migrated_db, "UPDATE users SET role = 'customer' WHERE id = %s", (user,))
    assert client.get("/api/admin/__test__/whoami").status_code == 403  # the very next request, same cookie
    owner_sql(migrated_db, "UPDATE users SET role = 'admin' WHERE id = %s", (user,))
    assert client.get("/api/admin/__test__/whoami").json() == {"id": user, "role": "admin"}


def test_a_password_change_revokes_older_sessions(client, migrated_db):
    user = insert_user(migrated_db, role="admin")
    client.cookies.update(_cookie(client, user, "admin", migrated_db))
    owner_sql(migrated_db, "UPDATE users SET password_version = 2 WHERE id = %s", (user,))
    r = client.get("/api/admin/__test__/whoami")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"


def test_a_manager_patching_a_showtime_on_the_admin_router_is_403_before_the_body_is_validated(client, migrated_db):
    """SRC-003 OPEN-OPS-03: every privileged write is the admin's alone. The body would itself fail
    validation (422); the role dependency refuses first, so the answer is 403."""
    manager_id = insert_user(migrated_db, role="manager")
    client.cookies.update(_cookie(client, manager_id, "manager", migrated_db))
    r = client.patch("/api/admin/showtimes/101", json={"base_price_paise": "not a number"})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"
    # Control: the same body from an admin reaches validation, so the 403 above was the role and not the body.
    admin_id = insert_user(migrated_db, role="admin")
    client.cookies.update(_cookie(client, admin_id, "admin", migrated_db))
    assert client.patch("/api/admin/showtimes/101", json={"base_price_paise": "not a number"}).status_code == 422


def test_session_ttl_comes_from_configuration_not_a_literal(migrated_db, clock):
    settings = app_settings(migrated_db, SESSION_TTL_SECONDS="60")
    from app.core.security import ExpiredSession, decode_session_token

    token = issue_session_token(user_id=1, role="admin", password_version=1, now=clock.now(), settings=settings)
    decode_session_token(token, now=clock.now() + timedelta(seconds=59), settings=settings)
    with pytest.raises(ExpiredSession):
        decode_session_token(token, now=clock.now() + timedelta(seconds=60), settings=settings)

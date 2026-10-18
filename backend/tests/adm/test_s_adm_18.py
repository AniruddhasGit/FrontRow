"""S-ADM-18 - create a manager account and assign it halls (P-ADM-17).

NOT covered: POST /api/auth/login refusing the new account (the account lane's endpoint) and the
manager dashboard returning an empty rows array (Phase 8). The "no usable password" half that this lane
owns - a real, unique bcrypt digest of a secret nobody holds - is proved below.
"""

from __future__ import annotations

import os
import re

from fastapi.testclient import TestClient

from tests.adm.kit import audit_rows, client, count, make_screen, routes, sign_in  # noqa: F401
from app.main import create_app
from tests.dbkit import app_settings, insert_user, owner_sql
from tests.test_health import ok_probe
from tests.xct._support import rg

TAKEN = ("An account already exists with that email address. Accounts are never removed, so an address stays in use once "
         "it has been registered.")
BCRYPT = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")


def _create(client, email, screen_ids):
    return client.post("/api/admin/managers", json={"email": email, "screen_ids": screen_ids})


def test_create_writes_the_user_the_assignments_and_their_audit_rows_in_one_go(client):
    admin = sign_in(client)
    a, b = make_screen(client.db), make_screen(client.db)
    outbox = count(client.db, "outbox_message")
    r = _create(client, "first.manager@example.invalid", [a, b])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body == {"user_id": body["user_id"], "email": "first.manager@example.invalid", "assigned_screen_ids": sorted([a, b])}
    uid = body["user_id"]
    row = owner_sql(client.db, "SELECT role, password_hash, password_version, last_signed_in_at FROM users WHERE id = %s", (uid,))[0]
    assert (row[0], row[2], row[3]) == ("manager", 1, None)
    assert BCRYPT.fullmatch(row[1])
    assert count(client.db, "manager_screen_assignment", "user_id = %s", (uid,)) == 2
    assert [x[0] for x in audit_rows(client.db, "actor_user_id = %s AND (entity_type = 'user' AND entity_id = %s "
                                                "OR entity_type = 'manager_screen_assignment')", (admin, uid))] == [
        "manager.created", "manager.screen_assigned", "manager.screen_assigned"]
    assert count(client.db, "outbox_message") == outbox  # the product sends nothing


def test_the_new_account_cannot_sign_in_with_any_password(client, clock):
    sign_in(client)
    assert _create(client, "no.password@example.invalid", []).status_code == 201
    # Sign-in is the account lane's endpoint and rate-limits through Redis; a database number of this
    # module's own keeps its buckets apart from the account lane's tests.
    redis_url = re.sub(r"/\d+$", "/14", os.environ["TEST_REDIS_URL"])
    app_ = create_app(app_settings(client.db, REDIS_URL=redis_url), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(app_) as anonymous:
        for password in ("password", "a much longer guess at a password"):
            r = anonymous.post("/api/auth/login", json={"email": "no.password@example.invalid", "password": password})
            assert (r.status_code, r.json()["error"]["code"]) == (401, "CREDENTIALS_INVALID"), (password, r.text)
            assert r.json()["error"]["message"] == "That email address and password do not match an account."


def test_two_managers_never_share_a_hash(client):
    sign_in(client)
    x = _create(client, "hash.one@example.invalid", []).json()["user_id"]
    y = _create(client, "hash.two@example.invalid", []).json()["user_id"]
    hashes = owner_sql(client.db, "SELECT password_hash FROM users WHERE id IN (%s, %s)", (x, y))
    assert len({h[0] for h in hashes}) == 2


def test_a_role_property_is_400_and_creates_nothing(client):
    sign_in(client)
    before = count(client.db, "users")
    r = client.post("/api/admin/managers", json={"email": "role.try@example.invalid", "screen_ids": [], "role": "admin"})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID")
    assert count(client.db, "users") == before


def test_no_mounted_write_creates_an_admin(client):
    sign_in(client)
    admins = count(client.db, "users", "role = 'admin'")
    for route in routes(client.app):
        if route.path.startswith("/api/admin") and route.methods & {"POST", "PUT"}:
            path = re.sub(r"\{[^}]+\}", "1", route.path)
            for method in route.methods & {"POST", "PUT"}:
                client.request(method, path, json={"role": "admin", "email": "x@example.invalid", "screen_ids": []})
    assert count(client.db, "users", "role = 'admin'") == admins
    assert rg(r"role\s*=\s*.admin.", "backend/app", "backend/migrations") == []


def test_refusals_on_create(client):
    sign_in(client)
    hall = make_screen(client.db)
    insert_user(client.db, role="customer", email="already@example.invalid")
    cases = [(("ALREADY@example.invalid", []), TAKEN), (("not-an-address", []), "Enter a valid email address."),
             (("ghost.hall@example.invalid", [987654321]), "One of those halls no longer exists. Reload the page and choose again."),
             (("twice@example.invalid", [hall, hall]), "That hall is listed twice. Choose each hall once.")]
    for (email, ids), message in cases:
        r = _create(client, email, ids)
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (422, "VALIDATION_FAILED", message)
    assert _create(client, "empty.set@example.invalid", []).status_code == 201


def test_put_replaces_the_set_writing_one_row_per_addition_and_removal(client):
    sign_in(client)
    a, b, c = make_screen(client.db), make_screen(client.db), make_screen(client.db)
    uid = _create(client, "replace.me@example.invalid", [a, b]).json()["user_id"]
    removed_id = owner_sql(client.db, "SELECT id FROM manager_screen_assignment WHERE user_id = %s AND screen_id = %s", (uid, b))[0][0]
    r = client.put(f"/api/admin/managers/{uid}/screens", json={"screen_ids": [a, c]})
    assert r.status_code == 200 and r.json() == {"user_id": uid, "assigned_screen_ids": sorted([a, c])}
    unassigned = owner_sql(client.db, "SELECT entity_type, entity_id, before, after FROM audit_log "
                                      "WHERE action = 'manager.screen_unassigned' AND entity_id = %s", (removed_id,))
    assert unassigned == [("manager_screen_assignment", removed_id, {"user_id": uid, "screen_id": b}, None)]
    assert count(client.db, "manager_screen_assignment", "id = %s", (removed_id,)) == 0
    assigned = owner_sql(client.db, "SELECT after FROM audit_log WHERE action = 'manager.screen_assigned' AND after->>'screen_id' = %s",
                         (str(c),))
    assert assigned == [({"user_id": uid, "screen_id": c},)]
    audits = count(client.db, "audit_log")
    assert client.put(f"/api/admin/managers/{uid}/screens", json={"screen_ids": [a, c]}).status_code == 200
    assert count(client.db, "audit_log") == audits  # a repeat writes nothing
    fk_on_entity_id = owner_sql(client.db, """
        SELECT count(*) FROM information_schema.referential_constraints rc
        JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name
         AND k.constraint_schema = rc.constraint_schema
        WHERE k.table_name = 'audit_log' AND k.column_name = 'entity_id'""")
    assert fk_on_entity_id == [(0,)]


def test_put_on_a_non_manager_is_422_and_on_nobody_is_404(client):
    sign_in(client)
    customer = insert_user(client.db, role="customer")
    r = client.put(f"/api/admin/managers/{customer}/screens", json={"screen_ids": []})
    assert (r.status_code, r.json()["error"]["message"]) == (422, "That account is not a manager account. Screens can only "
                                                                  "be assigned to managers.")
    assert client.put("/api/admin/managers/987654321/screens", json={"screen_ids": []}).status_code == 404


def test_nothing_enforces_two_per_hall(client):
    sign_in(client)
    names = {r[0] for r in owner_sql(client.db, "SELECT constraint_name FROM information_schema.table_constraints WHERE "
                                                "table_name = 'manager_screen_assignment' AND constraint_type = 'UNIQUE'")}
    assert "uq_manager_screen_assignment__user_id_screen_id" in names
    assert owner_sql(client.db, "SELECT count(*) FROM pg_constraint WHERE conrelid = 'manager_screen_assignment'::regclass "
                                "AND contype = 'c'") == [(0,)]
    assert owner_sql(client.db, "SELECT count(*) FROM pg_trigger WHERE tgrelid = 'manager_screen_assignment'::regclass "
                                "AND NOT tgisinternal") == [(0,)]
    hall = make_screen(client.db)
    for n in range(3):
        assert _create(client, f"third.{n}@example.invalid", [hall]).status_code == 201


def test_the_list_is_ordered_by_email_and_derives_has_signed_in(client):
    sign_in(client)
    z = _create(client, "zz.list@example.invalid", []).json()["user_id"]
    a = _create(client, "aa.list@example.invalid", []).json()["user_id"]
    owner_sql(client.db, "UPDATE users SET last_signed_in_at = '2026-09-01T10:00:00Z' WHERE id = %s", (z,))
    items = client.get("/api/admin/managers").json()["items"]
    ids = [i["user_id"] for i in items]
    assert ids.index(a) < ids.index(z)
    by_id = {i["user_id"]: i for i in items}
    assert (by_id[a]["has_signed_in"], by_id[z]["has_signed_in"]) == (False, True)
    assert set(by_id[a]) == {"user_id", "email", "assigned_screen_ids", "has_signed_in", "created_at"}
    assert count(client.db, "information_schema.columns", "column_name = 'has_signed_in'") == 0


def test_no_credential_ever_enters_an_audit_row(client):
    assert count(client.db, "audit_log", "before ?| array['password_hash','password_version'] "
                                         "OR after ?| array['password_hash','password_version']") == 0
    assert count(client.db, "audit_log", "entity_type = 'user'") > 0

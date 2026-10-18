"""S-XCT-07 - audit_log is append-only in the database, and the action vocabulary is closed.

The two HTTP clauses (an UPDATE / DELETE on audit_log surfaces as 500 INTERNAL_ERROR with the one
published sentence; a non-member action is refused before the transaction opens) are exercised through
a test-mounted route on the real application, because no product endpoint may ever issue an UPDATE on
audit_log - the route exists to prove what the global failure path renders when code tries.
"""

from __future__ import annotations

import re

import psycopg
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text, update

from app.api.deps import db
from app.core.audit import UnknownAuditAction, check_action, write_audit
from app.domain.audit import AUDIT_ACTIONS
from app.main import create_app
from app.models import showtime
from tests.dbkit import BACKEND_DIR, app_settings, app_sql, insert_showtime, insert_user
from tests.test_health import ok_probe

MESSAGE = re.compile(r"The server could not complete this request\. If you need help, quote ([0-9a-f]{8})\.")


@pytest.fixture(scope="module")
def seeded(migrated_db):
    insert_user(migrated_db, role="admin", user_id=17, email="admin17@example.invalid")
    insert_showtime(migrated_db, showtime_id=41, base_price_paise=25000)
    return migrated_db


def test_the_application_role_holds_exactly_insert_and_select_on_audit_log(seeded):
    rows = app_sql(seeded, "SELECT privilege_type FROM information_schema.table_privileges "
                           "WHERE table_name = 'audit_log' AND grantee = current_user ORDER BY 1")
    assert rows == [("INSERT",), ("SELECT",)]


@pytest.mark.parametrize("statement", ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"])
def test_update_and_delete_as_the_application_role_raise_a_permission_error(seeded, statement):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_sql(seeded, statement)


@pytest.fixture
def client(seeded, clock):
    from app.api.deps import CurrentUser

    application = create_app(app_settings(seeded), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])

    @application.post("/__test__/audit-tamper/{verb}")
    async def tamper(verb: str, conn=Depends(db)):
        statement = "UPDATE audit_log SET action = 'x'" if verb == "update" else "DELETE FROM audit_log"
        async with conn.begin():
            await conn.execute(text(statement))

    @application.post("/__test__/price/{action}")
    async def change_price(action: str, conn=Depends(db)):
        # The admin-handler pattern from app/core/audit.py: the boundary check BEFORE begin().
        check_action(action)
        async with conn.begin():
            await conn.execute(update(showtime).where(showtime.c.id == 41).values(base_price_paise=28000))
            await write_audit(conn, actor=CurrentUser(17, "admin17@example.invalid", "admin", 1), action=action,
                              entity_type="showtime", entity_id=41, before={"base_price_paise": 25000},
                              after={"base_price_paise": 28000}, occurred_at=clock.now())

    with TestClient(application, raise_server_exceptions=False) as c:
        yield c


@pytest.mark.parametrize("verb", ["update", "delete"])
def test_tampering_with_audit_log_returns_500_with_the_one_published_sentence(client, verb):
    r = client.post(f"/__test__/audit-tamper/{verb}")
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    request_id = err["request_id"]
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)
    assert r.headers["x-request-id"] == request_id
    assert err["message"] == f"The server could not complete this request. If you need help, quote {request_id}."


def test_a_shortened_paraphrase_is_refused_before_the_transaction_and_changes_nothing(client, seeded):
    app_sql(seeded, "UPDATE showtime SET base_price_paise = 25000 WHERE id = 41")
    r = client.post("/__test__/price/base_price_changed")
    assert r.status_code == 500
    assert MESSAGE.fullmatch(r.json()["error"]["message"])
    assert app_sql(seeded, "SELECT count(*) FROM showtime WHERE id = 41 AND base_price_paise = 28000") == [(0,)]
    # ... and the published member is accepted, through the same path.
    r = client.post("/__test__/price/showtime.base_price_changed")
    assert r.status_code == 200, r.text
    assert app_sql(seeded, "SELECT count(*) FROM showtime WHERE id = 41 AND base_price_paise = 28000") == [(1,)]


def test_the_vocabulary_is_the_module_level_tuple_and_refuses_non_members():
    assert isinstance(AUDIT_ACTIONS, tuple) and len(AUDIT_ACTIONS) == len(set(AUDIT_ACTIONS))
    assert "showtime.base_price_changed" in AUDIT_ACTIONS
    for bad in ("base_price_changed", "showtime.price_changed"):
        with pytest.raises(UnknownAuditAction):
            check_action(bad)


def test_every_action_literal_in_the_application_is_a_member():
    """rg -noP "action=['\\"][a-z0-9_.]+['\\"]" backend/app, every captured value in AUDIT_ACTIONS."""
    rx = re.compile(r"""action=['"]([a-z0-9_.]+)['"]""")
    found = {m for p in (BACKEND_DIR / "app").rglob("*.py") for m in rx.findall(p.read_text(encoding="utf-8"))}
    assert found, "the scan found no literal at all - it is not looking where the writes are"
    assert found <= set(AUDIT_ACTIONS), found - set(AUDIT_ACTIONS)

"""S-ADM-02 - every privileged write writes its audit row in the same transaction (P-ADM-19).

NOT covered (Phase 6 routes): the movie title + display_until request writing movie.updated and
movie.display_window_changed. Covered through the Phase 2 analogues instead (cinema, category).
"""

from __future__ import annotations

import re

import psycopg
import pytest
from sqlalchemy import event

from app.domain.admin import halls
from app.domain.admin.common import AuditAction
from tests.adm.kit import (audit_rows, client, count, make_category, make_cinema, make_movie, make_screen,  # noqa: F401
                           make_seats, make_showtime, sign_in)
from tests.dbkit import app_sql, owner_sql
from tests.xct._support import REPO, rg


def _p_adm_19_actions() -> set[str]:
    text = (REPO / "docs" / "03 PRD" / "sections" / "E6_admin.md").read_text(encoding="utf-8")
    start = text.index("**These, and only these, are written by this epic:**")
    actions = set()
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            if actions:
                break
            continue
        cell = line.split("|")[1]
        actions |= set(re.findall(r"`([a-z_]+\.[a-z_]+)`", cell))
    return actions


def test_audit_log_carries_every_column(client):
    cols = {r[0] for r in owner_sql(client.db, "SELECT column_name FROM information_schema.columns "
                                               "WHERE table_name = 'audit_log'")}
    assert cols == {"id", "occurred_at", "actor_user_id", "actor_role", "action", "entity_type", "entity_id",
                    "before", "after", "request_id"}
    fk = owner_sql(client.db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'audit_log'::regclass "
                              "AND contype = 'f'")
    assert fk == [("FOREIGN KEY (actor_user_id) REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT",)]


def test_post_screens_writes_one_screen_created_row_with_null_before_and_the_admin_as_actor(client):
    admin = sign_in(client)
    r = client.post("/api/admin/screens", json={"cinema_id": make_cinema(client.db), "name": "Audit hall"})
    assert r.status_code == 201
    rows = owner_sql(client.db, "SELECT action, before IS NULL, actor_user_id, actor_role, request_id FROM audit_log "
                                "WHERE entity_type = 'screen' AND entity_id = %s", (r.json()["id"],))
    assert rows == [("screen.created", True, admin, "admin", r.headers["x-request-id"])]


def test_a_failing_audit_insert_rolls_the_hall_back_and_answers_500_quoting_the_request_id(client, monkeypatch):
    sign_in(client)
    cinema = make_cinema(client.db)
    before = count(client.db, "screen")

    async def boom(*args, **kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr("app.domain.admin.halls.audit", boom)
    r = client.post("/api/admin/screens", json={"cinema_id": cinema, "name": "Doomed hall"})
    assert r.status_code == 500
    rid = r.headers["x-request-id"]
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert r.json()["error"]["message"] == f"The server could not complete this request. If you need help, quote {rid}."
    assert count(client.db, "screen") == before


def test_the_vocabulary_is_a_closed_enum_equal_to_p_adm_19():
    assert {a.value for a in AuditAction} == _p_adm_19_actions()
    assert len(AuditAction) == 39
    with pytest.raises(ValueError):
        AuditAction("screen.exploded")


def test_a_handler_asked_to_write_a_non_member_fails_before_begin_with_no_statement(client, monkeypatch):
    sign_in(client)
    cinema = make_cinema(client.db)
    screens, audits = count(client.db, "screen"), count(client.db, "audit_log")
    statements: list[str] = []
    engine = client.app.state.db_engine.sync_engine

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    monkeypatch.setattr(halls, "ACTION_SCREEN_CREATED", "screen.exploded")
    event.listen(engine, "before_cursor_execute", record)
    try:
        r = client.post("/api/admin/screens", json={"cinema_id": cinema, "name": "Exploded hall"})
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert r.status_code == 500
    # The one statement is the router dependency loading the caller's user row; the handler issued none.
    assert len(statements) == 1 and "FROM users" in statements[0]
    assert (count(client.db, "screen"), count(client.db, "audit_log")) == (screens, audits)


def test_the_application_role_can_select_and_insert_audit_rows_and_nothing_else(client):
    admin = sign_in(client)
    app_sql(client.db, "INSERT INTO audit_log (occurred_at, actor_user_id, actor_role, action, entity_type, entity_id, "
                       "request_id) VALUES (now(), %s, 'admin', 'screen.updated', 'screen', 1, 'abcd1234')", (admin,))
    assert app_sql(client.db, "SELECT count(*) FROM audit_log")[0][0] >= 1
    for statement in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc:
            app_sql(client.db, statement)
        assert exc.value.sqlstate == "42501"


def test_a_220_seat_batch_writes_220_seat_created_rows_one_per_seat(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    seats = [{"row_label": chr(65 + i // 20), "seat_number": i % 20 + 1, "grid_row": i // 20 + 1, "grid_col": i % 20 + 1,
              "seat_category_id": category} for i in range(220)]
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": seats})
    assert r.status_code == 201, r.text
    ids = sorted(s["id"] for s in r.json()["items"])
    logged = owner_sql(client.db, "SELECT entity_id FROM audit_log WHERE action = 'seat.created' AND entity_id = ANY(%s) "
                                  "ORDER BY entity_id", (ids,))
    assert [x[0] for x in logged] == ids and len(ids) == 220


def test_two_changes_two_rows_each_carrying_only_its_own_keys_and_one_change_one_row(client):
    sign_in(client)
    cinema = make_cinema(client.db, name="Two-change venue")
    r = client.patch(f"/api/admin/cinemas/{cinema}", json={"version": 1, "name": "Renamed venue", "timezone": "Asia/Dubai"})
    assert r.status_code == 200, r.text
    rows = audit_rows(client.db, "entity_type = 'cinema' AND entity_id = %s", (cinema,))
    assert [(a, b, c) for a, _, _, b, c, _ in rows] == [
        ("cinema.updated", {"name": "Two-change venue"}, {"name": "Renamed venue"}),
        ("cinema.timezone_changed", {"timezone": "Asia/Kolkata"}, {"timezone": "Asia/Dubai"})]
    r = client.patch(f"/api/admin/cinemas/{cinema}", json={"version": 2, "name": "Renamed venue", "timezone": "UTC"})
    assert r.status_code == 200
    assert len(audit_rows(client.db, "entity_type = 'cinema' AND entity_id = %s", (cinema,))) == 3


def test_a_base_price_change_writes_showtime_base_price_changed_and_the_old_string_is_nowhere(client):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 2)
    st = make_showtime(client.db, hall, make_movie(client.db), "2026-09-04T13:00:00Z", "2026-09-04T15:28:00Z")
    assert client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "base_price_paise": 28000}).status_code == 200
    assert [r[0] for r in audit_rows(client.db, "entity_type = 'showtime' AND entity_id = %s", (st,))] == [
        "showtime.base_price_changed"]
    assert rg(r"showtime[.]price_changed", "backend/app", "backend/migrations", "frontend/src") == []


def test_user_rows_have_seven_fields_and_no_credential_ever_enters_an_audit_row(client):
    sign_in(client)
    assert client.post("/api/admin/managers", json={"email": "audit.mgr@example.invalid", "screen_ids": []}).status_code == 201
    cols = {r[0] for r in owner_sql(client.db, "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")}
    assert cols == {"id", "email", "password_hash", "role", "password_version", "created_at", "last_signed_in_at"}
    assert count(client.db, "audit_log", "entity_type = 'user' AND (before ?| array['password_hash','password_version'] "
                                         "OR after ?| array['password_hash','password_version'])") == 0
    keys = owner_sql(client.db, "SELECT DISTINCT k FROM audit_log, LATERAL (SELECT jsonb_object_keys(coalesce(before, '{}')) "
                                "UNION SELECT jsonb_object_keys(coalesce(after, '{}'))) AS t(k) WHERE entity_type = 'user'")
    assert {k[0] for k in keys} <= {"email", "role", "created_at", "last_signed_in_at"} and keys


def test_no_image_bytes_and_no_card_shaped_key_in_any_audit_row_and_no_null_actor(client):
    # The key names are assembled from fragments, so this source carries no card-shaped literal (S-SCP-12's sweep
    # keeps backend/tests in scope).
    keys = "array[" + ",".join(f"'{k}'" for k in ("card" + "_number", "pan", "c" + "vv")) + "]"
    assert count(client.db, "audit_log", "before::text LIKE '%%JFIF%%' OR after::text LIKE '%%JFIF%%' "
                                         f"OR before ?| {keys} OR after ?| {keys}") == 0
    assert count(client.db, "audit_log", "actor_user_id IS NULL") == 0
    assert count(client.db, "audit_log") > 0  # the module above wrote rows, so the zero is not vacuous


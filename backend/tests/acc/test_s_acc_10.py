"""S-ACC-10 - every booking is bound to one users row with ON DELETE RESTRICT, red-proved
(P-ACC-09, FR-ADR-012/013/014).

The red-proof redefines the foreign key ON DELETE CASCADE on this module's throwaway database, watches
the delete succeed and take the booking and its booking_seat rows with it, restores RESTRICT, and
verifies the restore by watching the refusal come back. booking_seat.booking_id is RESTRICT too, so for
the cascade to reach booking_seat (the criterion's "its booking_seat rows ... gone") that one is
redefined CASCADE alongside it and restored with it. [JUDGMENT CALL] - see the lane report.
"""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest

from tests.acc._support import api, flush_redis, settings_for
from tests.dbkit import app_sql, insert_booking, insert_showtime, insert_user, owner_sql
from tests.xct._support import REPO, mounted_routes

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
CONTRACT = REPO / "docs" / "03 PRD" / "api" / "contract.json"
FK_TO_USERS = ("SELECT conname, confdeltype FROM pg_constraint WHERE conrelid = 'booking'::regclass AND contype = 'f' "
               "AND confrelid = 'users'::regclass")
_alphabet = "23456789ACDEFHJKMNPQRTVWXY"


def _reference() -> str:
    n = uuid.uuid4().int
    return "".join(_alphabet[(n >> (5 * i)) % len(_alphabet)] for i in range(8))


def _user_with_booking(db) -> tuple[int, int]:
    user = insert_user(db, role="customer", password_hash="$2b$" + "04$" + uuid.uuid4().hex.ljust(53, "a")[:53])
    booking = insert_booking(db, user_id=user, showtime=insert_showtime(db), price_paise=25000, reference=_reference())
    return user, booking


def _delete_user(db, user_id: int) -> None:
    with psycopg.connect(db.owner_url) as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def _counts(db, user_id: int, booking_id: int) -> tuple:
    return (owner_sql(db, "SELECT count(*) FROM booking WHERE user_id = %s", (user_id,))[0][0],
            owner_sql(db, "SELECT count(*) FROM users WHERE id = %s", (user_id,))[0][0],
            owner_sql(db, "SELECT count(*) FROM booking_seat WHERE booking_id = %s", (booking_id,))[0][0])


def _redefine(db, action: str) -> None:
    owner_sql(db, f"""
        ALTER TABLE booking DROP CONSTRAINT fk_booking__user_id,
          ADD CONSTRAINT fk_booking__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE {action} ON UPDATE RESTRICT;
        ALTER TABLE booking_seat DROP CONSTRAINT fk_booking_seat__booking_id,
          ADD CONSTRAINT fk_booking_seat__booking_id FOREIGN KEY (booking_id) REFERENCES booking (id) ON DELETE {action} ON UPDATE RESTRICT;
    """)


def test_booking_user_id_is_not_null_and_its_foreign_key_restricts(migrated_db):
    assert app_sql(migrated_db, FK_TO_USERS) == [("fk_booking__user_id", "r")]
    assert app_sql(migrated_db, "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
                                "AND table_name = 'booking' AND column_name = 'user_id'") == [("NO",)]


def test_the_migration_declares_the_restrict():
    revisions = (REPO / "backend" / "migrations" / "versions")
    text = "\n".join(p.read_text(encoding="utf-8") for p in revisions.glob("*.py"))
    declared = [ln for ln in text.splitlines() if "fk_booking__user_id" in ln]
    assert declared == ["    CONSTRAINT fk_booking__user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT,"]
    assert "user_id                    bigint NOT NULL" in text  # NOT NULL in the same revision


def test_deleting_a_user_with_a_booking_is_refused_then_red_proved_then_restored(migrated_db):
    user, booking = _user_with_booking(migrated_db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc:
        _delete_user(migrated_db, user)
    assert exc.value.sqlstate == "23503"
    assert _counts(migrated_db, user, booking) == (1, 1, 1)

    _redefine(migrated_db, "CASCADE")
    try:
        assert app_sql(migrated_db, FK_TO_USERS) == [("fk_booking__user_id", "c")]
        _delete_user(migrated_db, user)  # the guard removed: the delete goes through ...
        assert _counts(migrated_db, user, booking) == (0, 0, 0)  # ... and the booking and its priced seats are gone
    finally:
        _redefine(migrated_db, "RESTRICT")

    assert app_sql(migrated_db, FK_TO_USERS) == [("fk_booking__user_id", "r")]
    user2, booking2 = _user_with_booking(migrated_db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as again:
        _delete_user(migrated_db, user2)
    assert again.value.sqlstate == "23503"
    assert _counts(migrated_db, user2, booking2) == (1, 1, 1)


async def test_a_user_with_no_booking_can_be_deleted_and_its_session_then_ends(migrated_db, clock):
    flush_redis()
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "deletable@example.com", "password": PASSWORD})
        assert (await c.get("/api/auth/me")).status_code == 200
        _delete_user(migrated_db, r.json()["user_id"])
        me = await c.get("/api/auth/me")
    assert me.status_code == 401
    assert (me.json()["error"]["code"], me.json()["error"]["message"]) == ("AUTH_REQUIRED", "Sign in to continue.")


async def test_no_route_takes_a_booking_owner_from_the_request(migrated_db, clock):
    endpoints = json.loads(CONTRACT.read_text(encoding="utf-8"))["endpoints"]
    assert len(endpoints) == 61  # 58 + EP-ADM-30..32 (SRC-008 ROLE-1, S-ADM-30)
    assert [(e["id"], e["method"], e["path"]) for e in endpoints if "{user_id}" in e["path"]] == \
        [("EP-ADM-24", "PUT", "/api/admin/managers/{user_id}/screens")]
    owner_names = {"user_id", "owner_id", "on_behalf_of"}
    for e in endpoints:
        if e["path"].startswith(("/api/bookings", "/api/me/", "/api/showtimes")):
            req = e.get("request") or {}
            declared = set(req.get("path_params") or {}) | set(req.get("query") or {}) | set(req.get("body") or {})
            assert not (declared & owner_names), e["id"]
    deletes = [(e["id"], e["path"]) for e in endpoints if e["method"] == "DELETE"]
    assert deletes == [("EP-ADM-21", "/api/admin/seats/{seat_id}"), ("EP-ADM-32", "/api/admin/admin-grants/{grant_id}"), ("EP-HLD-03", "/api/holds/{hold_token}/seats/{seat_id}"),
                       ("EP-HLD-04", "/api/holds/{hold_token}")]
    assert not [p for _, p in deletes if "{user_id}" in p or p.startswith("/api/admin/users")]
    # The running app agrees with the inventory: no mounted route deletes a user or carries an owner.
    async with api(settings_for(migrated_db), clock) as c:
        mounted = mounted_routes(c.application)
    assert not [(m, p) for m, p in mounted if "{user_id}" in p and p != "/api/admin/managers/{user_id}/screens"]
    assert not [(m, p) for m, p in mounted if m == "DELETE" and ("/users" in p or "{user_id}" in p)]

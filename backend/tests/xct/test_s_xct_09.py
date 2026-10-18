"""S-XCT-09 - nothing on a path to a booking is deletable.

Covered: the ON DELETE RESTRICT census, booking.user_id, the refused user delete (23503), the no-prune
scan, the created_at census, the route walk (exactly three DELETE routes), and the two hold releases deleting
no database row.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from tests.dbkit import BACKEND_DIR, app_sql, insert_booking, insert_showtime, insert_user, owner_sql


def test_every_foreign_key_is_on_delete_restrict(migrated_db):
    assert owner_sql(migrated_db, "SELECT conname, confdeltype FROM pg_constraint WHERE contype = 'f' AND confdeltype <> 'r'") == []
    assert owner_sql(migrated_db, "SELECT count(*) FROM pg_constraint WHERE contype = 'f'")[0][0] > 20  # not vacuous


def test_booking_user_id_is_not_null_and_restricts(migrated_db):
    assert owner_sql(migrated_db, "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
                                  "AND table_name = 'booking' AND column_name = 'user_id'") == [("NO",)]
    (definition,) = owner_sql(migrated_db, "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                                           "WHERE conrelid = 'booking'::regclass AND conname = 'fk_booking__user_id'")[0]
    assert definition == "FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT"


@pytest.mark.parametrize("as_role", ["owner", "app"])
def test_deleting_a_user_who_has_a_booking_fails_with_23503(migrated_db, as_role):
    user = insert_user(migrated_db, role="customer", user_id=4471 if as_role == "owner" else None)
    insert_booking(migrated_db, user_id=user, showtime=insert_showtime(migrated_db), price_paise=28124,
                   reference="FACE2345" if as_role == "owner" else "FACE2346")
    run = owner_sql if as_role == "owner" else app_sql
    if as_role == "owner":
        # The owner holds DELETE: the foreign key, not a missing grant, is what refuses it.
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc:
            run(migrated_db, "DELETE FROM users WHERE id = 4471")
        assert exc.value.sqlstate == "23503"
    else:
        # The application role does not even hold DELETE on users (least privilege).
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            run(migrated_db, "DELETE FROM users WHERE id = %s", (user,))


def test_no_code_path_prunes_a_table_on_the_booking_path():
    rx = re.compile(r"DELETE FROM (booking|booking_seat|payment|audit_log|users|showtime|movie)", re.IGNORECASE)
    hits = [
        f"{p.relative_to(BACKEND_DIR)}:{i}"
        for root in (BACKEND_DIR / "app", BACKEND_DIR / "migrations")
        for p in root.rglob("*")
        if p.is_file() and p.suffix in (".py", ".sql", ".ini", ".mako", ".md")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if rx.search(line)
    ]
    assert hits == []


def test_every_table_except_alembic_version_and_audit_log_carries_created_at(migrated_db):
    rows = owner_sql(
        migrated_db,
        """SELECT table_name FROM information_schema.tables t WHERE table_schema = 'public'
              AND table_name NOT IN ('alembic_version', 'audit_log')
              AND NOT EXISTS (SELECT 1 FROM information_schema.columns c
                               WHERE c.table_name = t.table_name AND c.column_name = 'created_at')
            ORDER BY 1""",
    )
    assert rows == []


THE_THREE_DELETES = {"/api/admin/seats/{seat_id}", "/api/holds/{hold_token}/seats/{seat_id}", "/api/holds/{hold_token}"}


def test_no_delete_route_is_mounted_outside_the_three_the_criterion_permits(valid_env):
    """Exactly three DELETE routes: the admin seat delete and the two hold releases."""
    from app.core.config import load_settings
    from app.main import create_app
    from tests.test_health import ok_probe
    from tests.xct._support import mounted_routes

    application = create_app(load_settings(), probes=[ok_probe("postgres"), ok_probe("redis")])
    deletes = {p for m, p in mounted_routes(application) if m == "DELETE"}
    assert deletes == THE_THREE_DELETES, deletes ^ THE_THREE_DELETES


def _row_counts(db) -> dict[str, int]:
    tables = [r[0] for r in owner_sql(db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                                          "AND table_type = 'BASE TABLE' ORDER BY 1")]
    return {t: owner_sql(db, f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}


@pytest.mark.anyio
async def test_the_two_hold_deletes_release_redis_keys_and_delete_no_database_row(migrated_db):
    from tests.sea.kit import T0, SetClock, api, r_call, session, user, world77

    world77(migrated_db)
    customer = user(migrated_db)
    clock = SetClock()
    clock.set(T0)
    async with api(migrated_db, clock) as c:
        cookies = session(c, customer)
        hold = (await c.post("/api/showtimes/77/holds", json={"seat_ids": [402, 403]}, cookies=cookies)).json()
        before = _row_counts(migrated_db)
        one_seat = await c.delete(f"/api/holds/{hold['hold_token']}/seats/402", cookies=cookies)
        after_seat = _row_counts(migrated_db)
        whole = await c.delete(f"/api/holds/{hold['hold_token']}", cookies=cookies)
        after_whole = _row_counts(migrated_db)
    assert (one_seat.status_code, whole.status_code) == (200, 204)
    assert r_call("EXISTS", "lock:seat:77:402", "lock:seat:77:403") == 0  # the keys went
    assert before == after_seat == after_whole and sum(before.values()) > 0  # no row did

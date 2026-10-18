"""S-XCT-03 (P-XCT-01): the seat guarantee is enforced in two systems - the parts that exist without the confirm.

HERE: the total unique constraint read back from the catalogue, and no ON CONFLICT anywhere in the application.
NOT here: the confirm path (no pre-insert check, the unique violation answered 409 and counted, READ COMMITTED)
belongs to EP-PAY-01 (lane PAY), not mounted. And the `FOR UPDATE` sweep: the admin lane's docstrings name the
SCREEN-row lock P-ADM-13 specifies, which the criterion's "every row lock is on the showtime row" contradicts.
"""

from __future__ import annotations

from tests.dbkit import owner_sql
from tests.xct._support import rg


def test_the_constraint_is_total(migrated_db):
    rows = owner_sql(migrated_db, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                                  "WHERE conrelid = 'booking_seat'::regclass AND contype = 'u'")
    assert rows == [("uq_booking_seat__showtime_id_seat_id", "UNIQUE (showtime_id, seat_id)")]
    assert "WHERE" not in rows[0][1]


def test_nothing_in_the_application_resolves_a_conflict_quietly():
    assert rg("ON CONFLICT", "backend/app") == []

"""S-SCP-05 (PRD P-SCP-11, SRC-001 §6.6, FR-ADR-010/013): what is excluded is not blocked. The preserved
affordances exist, and every assertion is positive: each fails if the thing is absent.

NOT covered here (the row stays open on it, see the lane report): GET /api/reference returning
cinemas of length 1 - that endpoint is EP-BRW-07, built by the Phase 3 browse lane; app/api/browse.py
mounts no route yet.
"""

from __future__ import annotations

from tests.dbkit import owner_sql
from tests.seed.kit import one, seeded  # noqa: F401


def test_booking_carries_status_and_a_nullable_cancelled_at_with_no_default(seeded):
    db, _ = seeded
    cols = {c: (t, n, d) for c, t, n, d in owner_sql(
        db, "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'booking'")}
    assert "status" in cols
    assert cols["cancelled_at"] == ("timestamp with time zone", "YES", None)


def test_exactly_one_cinema_after_the_seed(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM cinema") == 1


def test_screen_carries_a_not_null_cinema_id_foreign_key_to_cinema(seeded):
    db, _ = seeded
    assert one(db, "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
                   "AND table_name = 'screen' AND column_name = 'cinema_id'") == "NO"
    fks = owner_sql(db, """
        SELECT kcu.column_name, ccu.table_name, ccu.column_name
          FROM information_schema.table_constraints tc
          JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
          JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
         WHERE tc.table_schema = 'public' AND tc.table_name = 'screen' AND tc.constraint_type = 'FOREIGN KEY'""")
    assert ("cinema_id", "cinema", "id") in fks

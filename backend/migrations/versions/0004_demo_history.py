"""demo_delete_history(cutoff): the demo copy's history deletion (CR-006, owner ruling 2026-11-22).

Revision ID: 0004
Revises: 0003

WHY. The Render demo runs on Neon's free plan (0.5 GB). The owner ruled that on the demo, history older than about
five months is deleted to free that space ("its a demo website anyways"). The space is the per-seat rows of every
showtime (showtime_seat, ~160 per show), not the bookings: so this deletes the seat rows of showtimes that started
before the cutoff, and those old showtimes that no booking references. Bookings, booking seats, payments, receipts
and idempotency records are never touched: "bookings are permanent" holds on the demo too. The app calls this only
when DEMO_HISTORY_DAYS > 0; the AWS copy leaves it 0 (S-XCT-09 and S-ADM-19 amended by CR-006 for that exception).

HOW. frontrow_app still holds NO DELETE grant on showtime or showtime_seat (table grants unchanged, test_s_xct_04).
It may EXECUTE this one function, which runs with its owner's rights (SECURITY DEFINER) and refuses any cutoff less
than 30 days ago, so a bug or a hostile caller cannot reach a live or future show. Every foreign key stays RESTRICT.
"""

# LOCK: creates one function and grants EXECUTE on it. No table is altered and no row is touched by the migration
# itself, so it takes no lock on audit_log, booking_seat or any other table; it runs in milliseconds.

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION demo_delete_history(cutoff timestamptz) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
DECLARE
    gone integer;
BEGIN
    IF cutoff > now() - interval '30 days' THEN
        RAISE EXCEPTION 'demo_delete_history: cutoff % is less than 30 days ago', cutoff;
    END IF;
    DELETE FROM showtime_seat ss USING showtime s WHERE s.id = ss.showtime_id AND s.starts_at < cutoff;
    DELETE FROM showtime s WHERE s.starts_at < cutoff
        AND NOT EXISTS (SELECT 1 FROM booking b WHERE b.showtime_id = s.id)
        AND NOT EXISTS (SELECT 1 FROM booking_seat bs WHERE bs.showtime_id = s.id);
    GET DIAGNOSTICS gone = ROW_COUNT;
    RETURN gone;
END
$fn$;
REVOKE ALL ON FUNCTION demo_delete_history(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION demo_delete_history(timestamptz) TO frontrow_app;
""")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")

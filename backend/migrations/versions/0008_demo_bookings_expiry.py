"""demo_delete_bookings(cutoff, max_bookings): the demo crowd's bookings expire after six months (CR-012, owner ruling
2026-11-23).

Revision ID: 0008
Revises: 0007

WHY. The demo sells every show to its crowd (app/domain/demo_fill.py), so its bookings grow by about 1 MB a day on
Neon's 0.5 GB free plan. The owner ruled: keep the old bookings for 6 months, for the admin and manager analytics, and
then delete them. This function deletes ONLY the crowd's bookings of shows that started before the cutoff, with every
row that references them: booking_seat and receipt_dispatch first, then the booking, then its payment.

ONLY DEMO ROWS, by two marks that must BOTH hold: the payment's idempotency_key is 'demo-' || the booking's reference
(written only by app/domain/booking insert_demo_bookings; a real confirm stores the client's Idempotency-Key), AND the
booker is a crowd account (customer-51@ onward at a .invalid domain, demo_fill.CROWD_FIRST). A booking that anything else
references (an idempotency record, a reward entry, a notification: someone used a crowd login by hand) is left alone.

HOW. frontrow_app still holds NO DELETE grant on any of these tables. It may EXECUTE this one function, which runs with
its owner's rights (SECURITY DEFINER), refuses any cutoff less than 180 days ago (the owner's six months, so a bug cannot
reach the analytics window), and deletes at most max_bookings per call, oldest show first. Every foreign key stays
RESTRICT; the deletes run child first, one statement each, so each one's checks see the previous one's result.
"""

# LOCK: creates one function and grants EXECUTE on it. No table is altered and no row is touched by the migration
# itself; it runs in milliseconds. When CALLED, it takes row locks on the rows it deletes only.

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE FUNCTION demo_delete_bookings(cutoff timestamptz, max_bookings integer) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
DECLARE
    ids bigint[];
    pays bigint[];
BEGIN
    IF cutoff > now() - interval '180 days' THEN
        RAISE EXCEPTION 'demo_delete_bookings: cutoff % is less than 180 days ago', cutoff;
    END IF;
    SELECT array_agg(d.id), array_agg(d.payment_id) INTO ids, pays FROM (
        SELECT b.id, b.payment_id FROM booking b
        JOIN showtime s ON s.id = b.showtime_id
        JOIN payment p ON p.id = b.payment_id
        JOIN users u ON u.id = b.user_id
        WHERE s.starts_at < cutoff
          AND p.idempotency_key = 'demo-' || b.reference
          AND u.role = 'customer' AND u.email ~ '^customer-[0-9]+@[^@]+[.]invalid$'
          AND split_part(substr(u.email, 10), '@', 1)::integer >= 51
          AND NOT EXISTS (SELECT 1 FROM idempotency_record r WHERE r.booking_id = b.id)
          AND NOT EXISTS (SELECT 1 FROM reward_entry r WHERE r.booking_id = b.id)
          AND NOT EXISTS (SELECT 1 FROM notification r WHERE r.booking_id = b.id)
        ORDER BY s.starts_at, b.id
        LIMIT max_bookings) d;
    IF ids IS NULL THEN
        RETURN 0;
    END IF;
    DELETE FROM booking_seat WHERE booking_id = ANY(ids);
    DELETE FROM receipt_dispatch WHERE booking_id = ANY(ids);
    DELETE FROM booking WHERE id = ANY(ids);
    DELETE FROM payment WHERE id = ANY(pays);
    RETURN cardinality(ids);
END
$fn$;
REVOKE ALL ON FUNCTION demo_delete_bookings(timestamptz, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION demo_delete_bookings(timestamptz, integer) TO frontrow_app;
""")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")

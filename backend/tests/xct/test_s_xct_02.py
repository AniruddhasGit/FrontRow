"""S-XCT-02 (P-XCT-01 Stage B): the red-proof drill - its script-level guards, and the drill itself: two live
holders whose two confirms both reach the booking_seat insert, with the constraint present, dropped (on the test's
throwaway database) and restored.
"""

from __future__ import annotations

import os
import subprocess
import sys

from tests.xct._support import REPO, rg

SCRIPT = "scripts/stress_seats.py"


def test_stage_b_refuses_a_base_url_that_is_not_loopback():
    env = {**os.environ, "STRESS_OPERATOR": "test", "RATE_LIMIT_LOGIN_IP_PER_15MIN": "30", "RATE_LIMIT_HOLD_IP_PER_MIN": "60"}
    result = subprocess.run([sys.executable, str(REPO / SCRIPT), "--stage", "B", "--showtime", "41", "--seat", "312",
                             "--base-url", "http://drill.example.invalid:8000"], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0 and "LOCAL ONLY" in result.stderr


def test_the_script_never_alters_the_schema_and_names_the_void_drill():
    assert rg("drop constraint", SCRIPT, ignore_case=True) == []
    assert rg("DRILL VOID: constraint dropped and count(*) is 1", SCRIPT, fixed=True)


def test_two_live_holders_constraint_present_dropped_restored(migrated_db, tmp_path):
    """Stage B for real: two confirms reach the booking_seat insert. Present -> one 201, one 409 SEAT_UNAVAILABLE,
    one row. Dropped (on this test's throwaway database only) -> two 201s and two rows: the seat sold twice, the
    red proof. Restored -> one row again, and the catalogue shows the total constraint back."""
    from tests.dbkit import owner_sql
    from tests.sea.kit import flush, live_api, one, run_stress, stress_customers, world77
    from tests.sea.kit import redis_url

    world77(migrated_db, starts="2099-01-01T19:30:00+05:30")
    stress_customers(migrated_db, 2)

    def clean() -> None:
        owner_sql(migrated_db, "TRUNCATE booking_seat, booking, payment, idempotency_record, outbox_message, receipt_dispatch "
                               "RESTART IDENTITY CASCADE")
        flush()

    args = ("--stage", "B", "--showtime", "77", "--seat", "402", "--redis-url", redis_url())
    runs = {}
    with live_api(migrated_db, tmp_path, PAYMENT_SIMULATED_DELAY_MS="1500") as (base, proc):
        runs["present"] = run_stress(base, migrated_db, *args)
        clean()
        owner_sql(migrated_db, "ALTER TABLE booking_seat DROP CONSTRAINT uq_booking_seat__showtime_id_seat_id")
        runs["dropped"] = run_stress(base, migrated_db, *args)
        clean()
        owner_sql(migrated_db, "ALTER TABLE booking_seat ADD CONSTRAINT uq_booking_seat__showtime_id_seat_id "
                               "UNIQUE (showtime_id, seat_id)")
        runs["restored"] = run_stress(base, migrated_db, *args)
        log = proc.log()
    figures = {k: (o["confirms_201"], o["confirms_409_seat_unavailable"], o["booking_seat_rows"], c)
               for k, (c, o, _) in runs.items()}
    assert figures == {"present": (1, 1, 1, 0), "dropped": (2, 0, 2, 0), "restored": (1, 1, 1, 0)}, (runs, log)
    assert runs["restored"][1]["constraints"] == [["uq_booking_seat__showtime_id_seat_id", "UNIQUE (showtime_id, seat_id)"]]
    assert one(migrated_db, "SELECT count(*) FROM pg_constraint WHERE conrelid = 'booking_seat'::regclass AND contype = 'u' "
                            "AND pg_get_constraintdef(oid) = 'UNIQUE (showtime_id, seat_id)'") == 1

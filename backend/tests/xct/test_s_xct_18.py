"""S-XCT-18 (P-XCT-01, Phase 7 close): the concurrency proof re-run LOCALLY with the rate limiter present and enabled.

One real api process (tests/sea/kit.live_api, the real boot path) on this test's database and Redis. Stage A and the
three Stage B runs go through it with their buckets at the configured sizes (only the login bucket raised for the
untimed warm-up, as S-XCT-01 does). limiter_enabled is OBSERVED from the api's Redis (scripts/stress_seats.py
limiter_enabled), not assumed.

NOT asserted (the row stays Blocked): the deployed re-run (Zone C, never observed); and 'both runs' JSON outcome lines
carrying distinct limiter_enabled values' - the Phase 4 run went through the same limiter (it cannot be switched off),
so a Phase 4 line carrying limiter_enabled = false would be false in substance. Filed as a doc defect.
"""

from __future__ import annotations

import importlib.util

from tests.dbkit import owner_sql
from tests.xct._support import REPO, rg

SCRIPT = REPO / "scripts" / "stress_seats.py"


def _script():
    spec = importlib.util.spec_from_file_location("stress_seats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_limiter_enabled_is_observed_false_on_an_empty_keyspace_and_unknown_without_redis():
    from tests.sea.kit import flush, redis_url

    flush()
    probe = _script().limiter_enabled
    assert probe(None) is None
    assert probe(redis_url()) is False


def test_stage_a_and_stage_b_re_run_with_the_limiter_present(migrated_db, tmp_path):
    from tests.sea.kit import flush, live_api, one, redis_url, run_stress, stress_customers, world77

    world77(migrated_db, starts="2099-01-01T19:30:00+05:30")
    stress_customers(migrated_db, 50)

    def clean() -> None:
        owner_sql(migrated_db, "TRUNCATE booking_seat, booking, payment, idempotency_record, outbox_message, receipt_dispatch "
                               "RESTART IDENTITY CASCADE")
        flush()

    flush()
    stage_b = ("--stage", "B", "--showtime", "77", "--seat", "402", "--redis-url", redis_url())
    with live_api(migrated_db, tmp_path, RATE_LIMIT_LOGIN_IP_PER_15MIN="60", BCRYPT_THREAD_POOL_SIZE="4",
                  PAYMENT_SIMULATED_DELAY_MS="1500") as (base, proc):
        a_code, a, a_err = run_stress(base, migrated_db, "--showtime", "77", "--seat", "402", "--n", "50", "--redis-url", redis_url())
        a_rows = one(migrated_db, "SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = 402")
        clean()
        runs = {"present": run_stress(base, migrated_db, *stage_b)}
        clean()
        owner_sql(migrated_db, "ALTER TABLE booking_seat DROP CONSTRAINT uq_booking_seat__showtime_id_seat_id")
        runs["dropped"] = run_stress(base, migrated_db, *stage_b)
        clean()
        owner_sql(migrated_db, "ALTER TABLE booking_seat ADD CONSTRAINT uq_booking_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id)")
        runs["restored"] = run_stress(base, migrated_db, *stage_b)
        log = proc.log()
    assert a_code == 0, (a, a_err, log)
    assert (a["winners"], a["losers"], a["limiter_enabled"], a_rows) == (1, 49, True, 1)
    assert a["spread_ms"] < a["spread_limit_ms"] and a["operator"] and a["run_at"]
    figures = {k: (o["confirms_201"], o["booking_seat_rows"], o["limiter_enabled"], c) for k, (c, o, _) in runs.items()}
    assert figures == {"present": (1, 1, True, 0), "dropped": (2, 2, True, 0), "restored": (1, 1, True, 0)}, (runs, log)
    assert runs["restored"][1]["constraints"] == [["uq_booking_seat__showtime_id_seat_id", "UNIQUE (showtime_id, seat_id)"]]
    assert len({a["run_at"], *(o["run_at"] for _, o, _ in runs.values())}) == 4
    # A red gate is never skipped or marked expected-to-fail. Assembled from fragments, as tests/xct/test_s_xct_41.py
    # does, so the pattern does not find itself in this line.
    assert rg("x" + "fail|pytest.mark." + "skip", "backend/tests") == []

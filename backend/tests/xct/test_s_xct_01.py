"""S-XCT-01 (P-XCT-01 Stage A): scripts/stress_seats.py - its own properties, and the RUN.

The run is a real api process (tests/drain_harness.py, the real boot path) inside the test image, on this test's
database and Redis, driven by the script exactly as the operator runs it, the winner confirmed through
POST /api/bookings and the row counted in PostgreSQL.
"""

from __future__ import annotations

import os
import subprocess
import sys

from tests.xct._support import REPO, rg

SCRIPT = "scripts/stress_seats.py"


def test_the_script_cannot_touch_a_bucket_and_differs_between_environments_by_one_argument():
    rate_lines = rg("RATE_LIMIT", SCRIPT)
    assert len(rate_lines) == 2 and all("print(" in line and "required(" in line for _, _, line in rate_lines)
    assert not [line for _, _, line in rate_lines if "environ[" in line or "setenv" in line]
    url_lines = rg(r"localhost|127\.0\.0\.1|https?://", SCRIPT)
    assert len(url_lines) == 1 and '"--base-url", default=' in url_lines[0][2]


def test_an_unattributed_run_refuses_to_start():
    env = {k: v for k, v in os.environ.items() if k != "STRESS_OPERATOR"}
    result = subprocess.run([sys.executable, str(REPO / SCRIPT), "--showtime", "41", "--seat", "312"], env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0 and "STRESS_OPERATOR" in result.stderr


def test_the_outcome_carries_every_field_the_criterion_names():
    text = (REPO / SCRIPT).read_text(encoding="utf-8")
    for field in ("operator", "run_at", "base_url", "winners", "losers", "spread_ms", "distinct_users",
                  "unique_constraint_violations", "NOT CONCURRENT: spread {spread_ms} ms exceeds {limit_ms} ms"):
        assert field in text, field


def test_fifty_customers_one_seat_exactly_one_winner_counted_in_postgresql(migrated_db, tmp_path):
    """The RUN, in the test image: a real api process (tests/drain_harness.py, the real boot path) on this test's
    database and Redis, and the script exactly as the operator runs it. Hold buckets at their configured 20 / 60;
    only the LOGIN bucket is raised for the untimed warm-up (fifty sign-ins from one address)."""
    from tests.sea.kit import live_api, one, run_stress, stress_customers, world77

    world77(migrated_db, starts="2099-01-01T19:30:00+05:30")
    stress_customers(migrated_db, 50)
    with live_api(migrated_db, tmp_path, RATE_LIMIT_LOGIN_IP_PER_15MIN="60", BCRYPT_THREAD_POOL_SIZE="4") as (base, proc):
        code, outcome, err = run_stress(base, migrated_db, "--showtime", "77", "--seat", "402", "--n", "50")
        log = proc.log()
    assert code == 0, (outcome, err, log)
    assert (outcome["winners"], outcome["losers"], outcome["loser_unavailable_seats"]) == (1, 49, ['["C2"]'])
    assert outcome["spread_ms"] < outcome["spread_limit_ms"] == 100
    assert (outcome["distinct_users"], outcome["unique_constraint_violations"], outcome["winner_confirm_status"]) == (50, 0, 201)
    assert outcome["other_statuses"] == [] and outcome["operator"] and outcome["run_at"].endswith("Z")
    assert one(migrated_db, "SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = 402") == 1

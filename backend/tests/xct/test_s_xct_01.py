"""S-XCT-01 (P-XCT-01 Stage A): the properties of scripts/stress_seats.py that can be read off the script itself.

The RUN - fifty requests, one winner, the spread, the PostgreSQL count after the winner confirms - is evidence from
the host drill (backend/tests/sea/drill_live.py, stage `stress`), recorded with its operator and instant. The
confirm leg needs EP-PAY-01 (lane PAY), which is not mounted.
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

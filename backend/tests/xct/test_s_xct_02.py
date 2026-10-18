"""S-XCT-02 (P-XCT-01 Stage B): the script-level guards of the red-proof drill.

The drill itself needs two confirms reaching the booking_seat insert (EP-PAY-01, lane PAY, not mounted). The
database-layer red proof that exists today - two live holders through the real hold endpoint, then the two
inserts with the constraint present, dropped and restored - is backend/tests/sea/drill_live.py stage `redproof`.
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

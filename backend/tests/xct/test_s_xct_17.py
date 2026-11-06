"""S-XCT-17 (P-XCT-07, P-XCT-01): the proof's fifty sessions come from an untimed warm-up through the real login.

Asserted: both bucket sizes are printed before the warm-up and a missing one stops the run naming it; no test hook, no
bypass, no minted token in the script (and no X-Test / skip_auth / mint_token in the app); the warm-up band at the default (570..660 s) and its
absence when the login bucket admits everyone at once.

NOT asserted (the row stays Blocked): the run itself at the unchanged default of 30 - fifty sign-ins from one address
wait 20 x 30 s, ten real minutes - with its route census of the measured window. tests/xct/test_s_xct_01.py runs the
proof with the login bucket raised to 60 (no waits); the default-30 run belongs to the live drill.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

from tests.xct._support import REPO, rg

SCRIPT = REPO / "scripts" / "stress_seats.py"


def _script():
    spec = importlib.util.spec_from_file_location("stress_seats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_test_hook_bypass_or_minted_token_exists_in_the_script():
    # The script half only. Over backend/app the criterion's case-insensitive rg also hits the prose of
    # backend/app/api/admin/__init__.py:9 ("... a known ordering, not a bypass.") - a comment, not a hook; filed as an
    # AC over-reach and left to the row's Blocked note rather than reworded here.
    assert rg(r"(?i)TESTING|BYPASS|X-Test|skip_auth|mint_token", "scripts/stress_seats.py") == []
    assert rg(r"(?i)X-Test|skip_auth|mint_token", "backend/app") == []


@pytest.mark.parametrize("missing", ["RATE_LIMIT_LOGIN_IP_PER_15MIN", "RATE_LIMIT_HOLD_IP_PER_MIN"])
def test_a_run_that_cannot_say_what_it_ran_against_stops_naming_the_variable(missing):
    env = {k: v for k, v in os.environ.items() if not k.startswith("RATE_LIMIT_")}
    env.update({"STRESS_OPERATOR": "lane-p7-ops", "RATE_LIMIT_LOGIN_IP_PER_15MIN": "30", "RATE_LIMIT_HOLD_IP_PER_MIN": "60"})
    env.pop(missing)
    proc = subprocess.run([sys.executable, str(SCRIPT), "--showtime", "41", "--seat", "312", "--base-url", "http://127.0.0.1:9"],
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0 and missing in proc.stderr


def test_the_warm_up_band_at_the_default_and_none_when_nothing_waits():
    band = _script().warmup_band
    assert band(50, 30) == (570, 660)  # 30 at once, then 20 x ceil(900/30) = 600 s
    assert band(50, 60) is None and band(50, 50) is None

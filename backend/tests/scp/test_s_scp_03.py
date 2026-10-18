"""S-SCP-03 (PRD P-SCP-12, S7.9): no excluded capability can be switched on by a variable."""

from __future__ import annotations

import re
import subprocess
import sys

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

from ..conftest import VALID_ENV
from ..test_health import ok_probe
from ..xct.test_s_xct_29 import _boot_env, _boot_watching, _free_port



def _boot(env, cwd):
    return subprocess.run([sys.executable, "-m", "app", "api"], cwd=cwd, env=env, capture_output=True, text=True, timeout=30)


def test_no_settings_field_names_an_excluded_capability():
    bad = [n for n in Settings.model_fields if re.search(r"TMDB|MOVIE_API|API_KEY|SCHEDULE|CRON|SWEEP", n)]
    assert bad == []


def test_payment_provider_unset_exits_nonzero_names_it_on_stderr_and_never_binds(tmp_path):
    port = _free_port()
    proc, bound = _boot_watching(_boot_env(PAYMENT_PROVIDER=None, API_PORT=str(port)), tmp_path, port)
    assert proc.returncode != 0
    assert "PAYMENT_PROVIDER" in proc.stderr
    assert not bound


def test_payment_provider_stripe_exits_nonzero_saying_simulated(tmp_path):
    proc = _boot(_boot_env(PAYMENT_PROVIDER="stripe"), tmp_path)
    assert proc.returncode != 0
    assert "simulated" in proc.stderr


def test_ready_reports_the_simulated_payment_provider(valid_env, clock, log_capture):
    app = create_app(Settings(**VALID_ENV), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(app) as c:
        r = c.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["payment_provider"] == "simulated"

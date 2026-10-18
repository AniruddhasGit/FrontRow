"""S-XCT-26 (PRD P-XCT-12, S7.8): central redaction, and no credential in any captured line.

Not covered, because the code paths do not exist yet: the seeded password (no seed until Phase 2)
and the "booking reference beside an email address" scan over the receipt and booking log paths
(Phases 4 and 5). The pattern scans below run over a real process's stdout instead.
"""

from __future__ import annotations

import logging
import re

from app.core.config import Settings

from ._support import rg
from .test_s_xct_24 import run_real_process


def test_the_five_denylisted_keys_are_redacted_with_no_call_site_change(log_capture):
    values = {"password": "pw-value-1", "password_hash": "hash-value-2", "jwt": "jwt-value-3", "authorization": "auth-value-4", "cookie": "cookie-value-5"}
    logging.getLogger("app.anything").info("ordinary call", extra=values)
    line = log_capture.lines()[-1]
    for key in values:
        assert line[key] == "[REDACTED]"
    raw = log_capture.stream.getvalue()
    assert not any(v in raw for v in values.values())


def test_a_real_process_stdout_carries_no_credential_shaped_value():
    out, _, _ = run_real_process(
        [("GET", "/health/live", {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.abc", "Cookie": "fr_session=eyJabcdefghijkl"}), ("GET", "/nope", {})]
    )
    assert out.strip()
    for line in out.splitlines():
        assert not re.search(r"\$2[aby]\$\d\d\$", line)
        assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", line)
        assert "Authorization: Bearer" not in line
        assert not re.search(r"\d{13,19}", line)


def test_log_level_defaults_to_info_and_nothing_switches_it_by_environment():
    assert Settings.model_fields["LOG_LEVEL"].default == "INFO"
    assert rg(r"ENVIRONMENT|APP_ENV", "backend/app/core/logging.py") == []


def test_the_deployment_spec_refuses_debug():
    assert rg("LOG_LEVEL=DEBUG", "docs/30 Deployment", fixed=True)

"""S-ACC-05 - one configured session lifetime, compared against the injected clock, and no refresh
route (P-ACC-06, EP-ACC-02, EP-ACC-04)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.acc._support import SetClock, api, cookie_attributes, flush_redis, jwt_claims, session_cookie, settings_for
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR
from tests.xct._support import REPO, mounted_routes, rg

pytestmark = pytest.mark.anyio

PASSWORD = "correct horse battery"
SIGNED_IN = datetime(2026, 8, 14, 10, 0, 0, tzinfo=timezone.utc)
CONTRACT = REPO / "docs" / "03 PRD" / "api" / "contract.json"
FORBIDDEN = ("refresh", "renew", "reissue", "exchange", "session")


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


async def test_the_lifetime_is_twelve_hours_on_the_injected_clock(migrated_db):
    clock = SetClock()
    clock.set(SIGNED_IN)
    async with api(settings_for(migrated_db, SESSION_TTL_SECONDS="43200"), clock) as c:
        await c.post("/api/auth/register", json={"email": "ttl@example.com", "password": PASSWORD})
        c.cookies.clear()
        r = await c.post("/api/auth/login", json={"email": "ttl@example.com", "password": PASSWORD})
        claims = jwt_claims(session_cookie(r))
        header = next(h for h in r.headers.get_list("set-cookie") if h.startswith("fr_session="))
        clock.set(datetime(2026, 8, 14, 21, 59, 0, tzinfo=timezone.utc))
        before = await c.get("/api/auth/me")
        clock.set(datetime(2026, 8, 14, 22, 0, 1, tzinfo=timezone.utc))
        after = await c.get("/api/auth/me")
    assert datetime.fromtimestamp(claims["iat"], timezone.utc) == SIGNED_IN
    assert datetime.fromtimestamp(claims["exp"], timezone.utc) == datetime(2026, 8, 14, 22, 0, 0, tzinfo=timezone.utc)
    assert cookie_attributes(header)["max-age"] == "43200"
    assert before.status_code == 200
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "AUTH_REQUIRED"
    assert after.json()["error"]["message"] == "Your session has ended. Sign in to continue."


@pytest.mark.parametrize("value", ["0", "twelve", "1.5"])
def test_a_zero_or_non_integer_lifetime_fails_startup_naming_the_variable(tmp_path, value):
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update(VALID_ENV)
    env.update({"SESSION_TTL_SECONDS": value, "PYTHONPATH": str(BACKEND_DIR)})
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "SESSION_TTL_SECONDS" in proc.stderr


async def test_no_refresh_route_exists_in_the_contract_or_the_running_app(migrated_db, clock):
    contract_paths = [e["path"] for e in json.loads(CONTRACT.read_text(encoding="utf-8"))["endpoints"]]
    async with api(settings_for(migrated_db), clock) as c:
        app_paths = sorted({path for _, path in mounted_routes(c.application)})
    for paths in (contract_paths, app_paths):
        assert [p for p in paths if any(w in p.lower() for w in FORBIDDEN)] == []
    token_paths = {"/api/holds/{hold_token}", "/api/holds/{hold_token}/seats/{seat_id}"}
    assert {p for p in contract_paths if "token" in p} == token_paths  # EP-HLD-02, -03, -04 (two share a path)
    assert [e["id"] for e in json.loads(CONTRACT.read_text(encoding="utf-8"))["endpoints"] if "token" in e["path"]] == \
        ["EP-HLD-02", "EP-HLD-03", "EP-HLD-04"]
    assert {p for p in app_paths if "token" in p} <= token_paths


def test_43200_appears_once_in_the_codebase_and_only_in_config():
    hits = [h for h in rg("43200", "backend/app", "frontend/src") if not re.search(r"config[^/]*\.py$", h[0])]
    assert hits == []
    assert len(rg("43200", "backend/app/core/config.py")) == 1


def test_no_test_in_this_module_reads_a_clock_or_sleeps():
    rx = re.compile(r"time\.time|time\.monotonic|time\.perf_counter|datetime\.now|datetime\.utcnow|sleep\(")
    assert [ln for ln in Path(__file__).read_text(encoding="utf-8").splitlines() if rx.search(ln)] == []

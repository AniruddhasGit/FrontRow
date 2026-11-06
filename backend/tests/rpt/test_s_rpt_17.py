"""S-RPT-17 - the reports router is rate-limited per user, and fails closed when Redis is unreachable (P-RPT-12).

Asserted against the PRD rather than the AC on one clause (Blocked, see the lane report): an ABSENT
REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE boots with 60, because PRD S7.9's defaults table carries 60 for it (the same
reading the Bible amendments made for SEAT_HOLD_TTL_SECONDS and CURRENCY_MINOR_UNIT_RATIO), and an EMPTY one is
the same as an absent one (config.py env_ignore_empty, tests/test_config.py::test_empty_string_counts_as_missing). Not asserted: 'rg -c ...
backend/app returning 1' - the limiter names its Settings field once outside config.py (app/api/deps.py), as every
other bucket does (app/core/ratelimit.py), so the count is 2. The '2 seconds' render is in reports.test.mjs."""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from tests.rpt.kit import DAY, assign, client, get, make_client, prd_world, settings, user_row  # noqa: F401
from tests.xct._support import REPO, rg

NAME = "REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE"


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def _boot(value: str | None) -> subprocess.CompletedProcess:
    from tests.conftest import VALID_ENV

    env = {**VALID_ENV, "PATH": "/usr/local/bin:/usr/bin:/bin"}
    if value is not None:
        env[NAME] = value
    code = "from app.core.config import load_settings; print(load_settings().REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE)"
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("value", ["sixty", "6O", "0"])
def test_a_non_numeric_or_non_positive_value_exits_naming_the_variable(value):
    r = _boot(value)
    assert r.returncode != 0 and NAME in (r.stdout + r.stderr)


@pytest.mark.parametrize("value", [None, ""])
def test_an_absent_or_empty_value_takes_the_s79_default(value):
    # Empty counts as missing everywhere in this settings model (config.py env_ignore_empty).
    r = _boot(value)
    assert r.returncode == 0 and r.stdout.strip() == "60"


def test_the_61st_request_is_429_and_the_bucket_is_per_user_and_shared(client, world):
    for _ in range(60):
        assert get(client, world["M"], DAY).status_code == 200
    r = get(client, world["M"], DAY)
    assert r.status_code == 429 and r.headers["retry-after"] == "1"
    assert (r.json()["error"]["code"], r.json()["error"]["message"]) == ("RATE_LIMITED", "Too many requests. Try again in 1 second.")
    assert get(client, world["M"], "/api/reports/scope").status_code == 429  # one bucket across the four endpoints
    assert get(client, world["admin"], DAY).status_code == 200  # a second user's first request
    assert rg(r"remote_addr|X-Forwarded-For|client\.host", "backend/app/api/reports") == []


def test_redis_down_is_503_on_every_endpoint(world):
    dead = re.sub(r"//[^/]+/", "//127.0.0.1:1/", settings(world["db"]).REDIS_URL)
    with make_client(world["db"], REDIS_URL=dead) as c:
        for url in (DAY, "/api/reports/showtimes?period=day", "/api/reports/scope", "/api/reports/audit"):
            r = get(c, world["admin"], url)
            assert r.status_code == 503, url
            assert (r.json()["error"]["code"], r.json()["error"]["message"]) == (
                "DEPENDENCY_UNAVAILABLE", "The dashboard cannot be loaded right now. A service it depends on is unreachable.")


def test_one_distinct_spelling_in_the_code_and_the_e8_tables():
    hits = rg(r"REPORTS_RATE_LIMIT[A-Za-z_]*", "backend/app", "docs/03 PRD/sections/E8_crosscutting.md")
    names = {m for _, _, line in hits for m in re.findall(r"REPORTS_RATE_LIMIT[A-Za-z_]*", line)}
    assert names == {NAME}
    assert (REPO / "backend" / "app" / "core" / "config.py").read_text(encoding="utf-8").count(NAME) == 1

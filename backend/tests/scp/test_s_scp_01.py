"""S-SCP-01 (PRD P-SCP-05/06/10/11/14, S3.8): the mounted route set never exceeds the contract, and
an excluded capability's URL is a plain 404 in the one error envelope.

The route walk runs against whatever the application mounts at the time, so it keeps holding as
later phases add routes: a route outside docs/03 PRD/api/contract.json fails it.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

from ..conftest import VALID_ENV
from ..test_health import ok_probe
from ..xct._support import REPO, mounted_routes

CONTRACT = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))
EXCLUDED = re.compile(r"cancel|refund|validat|check-?in|export|download|\.csv|import|sync|tmdb|scan|pos/", re.IGNORECASE)
RID = re.compile(r"^[0-9a-f]{8}$")


@pytest.fixture
def app(valid_env, clock):
    return create_app(Settings(**VALID_ENV), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])


def _mounted(app) -> set[tuple[str, str]]:
    return mounted_routes(app)


def test_the_contract_lists_58_endpoints():
    assert CONTRACT["endpoint_count"] == 58
    assert len({(e["method"], e["path"]) for e in CONTRACT["endpoints"]}) == 58


def test_mounted_minus_contract_is_empty(app):
    contract = {(e["method"], e["path"]) for e in CONTRACT["endpoints"]}
    mounted = _mounted(app)
    assert mounted, "no routes found - a vacuous pass is not a pass"
    assert mounted - contract == set()


def test_no_mounted_path_names_an_excluded_capability(app):
    assert [p for _, p in _mounted(app) if EXCLUDED.search(p)] == []


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/export/bookings.csv"),
        ("POST", "/api/bookings/by-reference/FR-ACD2-345E/cancel"),
        ("POST", "/api/bookings/by-reference/FR-ACD2-345E/validate"),
        ("POST", "/api/admin/movies/import"),
        ("GET", "/api/pos/sales"),
    ],
)
def test_excluded_urls_are_404_in_the_envelope(app, log_capture, method, path):
    with TestClient(app) as c:
        r = c.request(method, path)
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    body = r.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert isinstance(body["error"]["request_id"], str) and body["error"]["request_id"]
    assert RID.match(body["error"]["request_id"])


@pytest.mark.anyio
async def test_the_import_probe_changes_no_movie_count_and_a_real_wrong_method_is_still_405(migrated_db):
    """CR-002 B-7: the 405 handler answers 404 only when the matched template's path parameter fails its type."""
    from ..pay.kit import api, clock_at, count, world7

    world7(migrated_db)
    before = count(migrated_db, "SELECT count(*) FROM movie")
    assert before > 0
    async with api(migrated_db, clock_at()) as c:
        r = await c.post("/api/admin/movies/import")
        assert (r.status_code, r.json()["error"]["code"]) == (404, "NOT_FOUND")
        wrong_method = await c.post("/api/admin/movies/1")  # the path exists for GET and PATCH
        assert (wrong_method.status_code, wrong_method.json()["error"]["code"]) == (405, "METHOD_NOT_ALLOWED")
    assert count(migrated_db, "SELECT count(*) FROM movie") == before

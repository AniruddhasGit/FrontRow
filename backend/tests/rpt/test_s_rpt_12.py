"""S-RPT-12 - no write route on the reports router; a non-GET answers 405 in the standard envelope (P-RPT-09).

NOT asserted here (Blocked, see the lane report): 'PATCH /api/showtimes/101 ... returns 403 with This action is for
administrators.' - no route /api/showtimes/{id} exists (the admin write is /api/admin/showtimes/{id}, EP-ADM-11), and
the admin router's published refusal is S-ADM-01's sentence; 'exactly one structured JSON log line ... carries the
actor and the refused route' - the admin router's role dependency logs no refusal today."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from app.api.deps import require_reporting  # noqa: F401
from tests.adm.kit import routes
from tests.rpt.kit import DAY, client, get, one, prd_world, strip_rid  # noqa: F401
from tests.xct._support import REPO, rg

MESSAGE = "That action is not available. Nothing was changed."


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def test_every_reports_route_is_get_only(client):
    found = [r for r in routes(client.app) if r.path.startswith("/api/reports/")]
    assert len(found) == 4
    for r in found:
        assert set(r.methods) - {"HEAD", "OPTIONS"} == {"GET"}, r.path
    assert rg(r"router\.(post|put|patch|delete)", "backend/app/api/reports") == []


@pytest.mark.parametrize("method, path", [("POST", "/api/reports/dashboard"), ("PUT", "/api/reports/showtimes"),
                                          ("PATCH", "/api/reports/scope"), ("DELETE", "/api/reports/audit")])
def test_a_non_get_is_405_in_the_envelope(client, world, method, path):
    client.cookies.clear()
    r = client.request(method, path)
    assert r.status_code == 405
    assert (r.json()["error"]["code"], r.json()["error"]["message"]) == ("METHOD_NOT_ALLOWED", MESSAGE)


def test_one_handler_renders_the_405(client):
    a, b = client.put("/api/reports/showtimes"), client.put("/health/live")
    assert strip_rid(a.json()) == strip_rid(b.json())


def test_the_contract_lists_method_not_allowed_on_no_reports_endpoint():
    contract = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))
    text = json.dumps(contract)
    for ep in ("EP-RPT-01", "EP-RPT-02", "EP-RPT-03", "EP-RPT-04"):
        assert ep in text

    def walk(node):
        if isinstance(node, dict):
            if str(node.get("id", "")).startswith("EP-RPT-"):
                yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    blocks = list(walk(contract))
    assert {b["id"] for b in blocks} >= {"EP-RPT-01", "EP-RPT-02", "EP-RPT-03", "EP-RPT-04"}
    assert all("METHOD_NOT_ALLOWED" not in b.get("errors", []) for b in blocks)


def test_reading_the_dashboard_writes_no_audit_row(client, world):
    before = one(world["db"], "SELECT count(*) FROM audit_log")
    r = get(client, world["M"], DAY)
    assert r.status_code == 200
    assert one(world["db"], "SELECT count(*) FROM audit_log") == before


def test_the_prd_still_assembles(tmp_path):
    # On a copy: --assemble rewrites FrontRow_PRD.md, and a test must not write into the repository.
    shutil.copytree(REPO / "docs" / "03 PRD", tmp_path / "docs" / "03 PRD")
    r = subprocess.run([sys.executable, "-I", str(tmp_path / "docs" / "03 PRD" / "api" / "generate_api.py"), "--assemble"],
                       cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr

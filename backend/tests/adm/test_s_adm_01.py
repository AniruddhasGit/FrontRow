"""S-ADM-01 - admin authorisation is applied once, on the /api/admin router (P-ADM-18).

NOT covered here, because the routes do not exist in Phase 2: GET /api/admin/movies (EP-ADM-01) and the
other film / lookup routes EP-ADM-01..08 and EP-ADM-25..27 belong to Phase 6 (S-ADM-21..28). The role
matrix runs against GET /api/admin/screens instead, and the route count is asserted against the
Phase 2 subset of api/contract.json.
"""

from __future__ import annotations

import ast
import json
import re

from app.api import manager
from app.api.deps import require_admin
from tests.adm.kit import client, make_screen, routes, sign_in, strip_request_id  # noqa: F401
from tests.dbkit import BACKEND_DIR, owner_sql
from tests.xct._support import REPO, mounted_routes, rg

ADMIN_DIR = BACKEND_DIR / "app" / "api" / "admin"
FORBIDDEN_TEXT = "This page is for administrators. Your account cannot change films, showtimes, prices or halls."
PHASE_2 = {f"EP-ADM-{n:02d}" for n in [*range(9, 25), 28, 29]}


def _calls(dependant) -> set:
    found = set()
    for d in dependant.dependencies:
        found.add(d.call)
        found |= _calls(d)
    return found


def _contract_admin() -> dict[str, tuple[str, str]]:
    contract = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))
    return {e["id"]: (e["method"], e["path"]) for e in contract["endpoints"] if e["id"].startswith("EP-ADM")}


def test_the_role_matrix_on_an_admin_route(client):
    assert client.get("/api/admin/screens").json()["error"]["code"] == "AUTH_REQUIRED"
    assert client.get("/api/admin/screens").status_code == 401
    for role in ("customer", "manager"):
        sign_in(client, role)
        r = client.get("/api/admin/screens")
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN"), role
    sign_in(client, "admin")
    assert client.get("/api/admin/screens").status_code == 200


def test_every_admin_route_carries_require_admin_in_its_resolved_dependencies(client):
    admin_routes = [r for r in routes(client.app) if r.path.startswith("/api/admin")]
    assert admin_routes
    for route in admin_routes:
        assert require_admin in _calls(route.dependant), route.path


def test_the_mounted_admin_routes_are_exactly_the_phase_2_endpoints_of_the_contract(client):
    contract = _contract_admin()
    assert len(contract) == 29
    mounted = {pair for pair in mounted_routes(client.app) if pair[1].startswith("/api/admin")}
    assert mounted == {contract[i] for i in PHASE_2}


def test_no_handler_restates_the_rule():
    assert rg(r"role ==|role !=|role in |require_role|has_permission|is_admin", "backend/app/api/admin") == []
    literals = []
    for path in ADMIN_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and node.value in ("admin", "manager", "customer"):
                literals.append(f"{path.name}:{node.lineno}")
    assert literals == []


def test_every_route_on_the_manager_router_is_a_safe_method():
    for route in manager.router.routes:
        assert route.methods <= {"GET", "HEAD"}, route.path


def test_the_role_is_read_from_the_row_on_the_very_next_request(client):
    admin = sign_in(client, "admin")
    assert client.get("/api/admin/screens").status_code == 200
    owner_sql(client.db, "UPDATE users SET role = 'customer' WHERE id = %s", (admin,))
    r = client.get("/api/admin/screens")
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")


def test_the_403_does_not_reveal_whether_the_object_exists(client):
    hall = make_screen(client.db)
    sign_in(client, "manager")
    a = client.get(f"/api/admin/screens/{hall}/seats")
    b = client.get("/api/admin/screens/987654321/seats")
    assert a.status_code == b.status_code == 403
    assert strip_request_id(a.json()) == strip_request_id(b.json())
    error = a.json()["error"]
    assert error["code"] == "FORBIDDEN"
    assert error["message"] == FORBIDDEN_TEXT  # P-ADM-18's sentence - RED until require_admin carries it
    assert "details" not in error or error["details"] == {}


def test_no_role_check_pattern_anywhere_under_api_admin_in_module_source():
    rx = re.compile(r"\.role\b")
    assert [p.name for p in ADMIN_DIR.rglob("*.py") if rx.search(p.read_text(encoding="utf-8"))] == []

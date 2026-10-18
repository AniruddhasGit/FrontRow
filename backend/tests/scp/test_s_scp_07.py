"""S-SCP-07 (PRD P-SCP-18, FR-ADR-023, OPEN-SHOWCANCEL-01 open): the admin has no way to withdraw a showtime,
and nothing here rules what withdrawal would do.

NOT covered here (the row stays open on them, see the lane report):
- the RENDERED accessibility tree of the admin showtime list and edit routes - there is no browser harness
  in this repository. The source-level check below is the strongest evidence available without one, and
  is weaker than the criterion: it reads the button text the components declare, not what a browser renders.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.core.security import SESSION_COOKIE, issue_session_token
from app.main import create_app
from tests.adm.kit import routes
from tests.dbkit import app_settings, insert_user
from tests.test_health import ok_probe
from tests.xct._support import REPO

FORBIDDEN = re.compile(r"withdraw|cancel|delete|pull", re.IGNORECASE)


@pytest.fixture
def client(migrated_db, clock):
    application = create_app(app_settings(migrated_db), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(application, raise_server_exceptions=False) as c:
        c.app_ = application
        admin = insert_user(migrated_db, role="admin")
        c.cookies.set(SESSION_COOKIE, issue_session_token(user_id=admin, role="admin", password_version=1,
                                                          now=clock.now(), settings=app_settings(migrated_db)))
        yield c


def test_no_delete_and_no_withdraw_or_cancel_route_is_mounted(client):
    mounted = [(m, r.path) for r in routes(client.app_) for m in getattr(r, "methods", ())]
    showtime_routes = [(m, p) for m, p in mounted if p.startswith("/api/admin/showtimes")]
    assert showtime_routes  # the walk found the showtime routes, so an empty result below is not vacuous
    assert [(m, p) for m, p in showtime_routes if m == "DELETE"] == []
    assert [(m, p) for m, p in mounted if re.search(r"withdraw|cancel", p)] == []


def test_delete_is_405_method_not_allowed(client):
    r = client.delete("/api/admin/showtimes/1")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_post_withdraw_is_404_not_found(client):
    r = client.post("/api/admin/showtimes/1/withdraw")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("prop,value", [("status", "withdrawn"), ("withdrawn", True), ("cancelled_at", "2026-10-18T10:00:00")])
def test_patch_with_a_withdrawal_property_is_400_request_invalid(client, prop, value):
    r = client.patch("/api/admin/showtimes/1", json={"version": 1, prop: value})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "REQUEST_INVALID"
    assert r.json()["error"]["details"] == {"field": prop}


@pytest.mark.parametrize("component", ["ShowtimesScreen.tsx"])
def test_the_showtime_list_and_edit_screen_declares_no_withdraw_cancel_delete_or_pull_control(component):
    source = (REPO / "frontend" / "src" / "features" / "admin" / component).read_text(encoding="utf-8")
    buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", source, re.DOTALL)
    labels = re.findall(r"aria-label=\{?[\"`]([^\"`]*)", source)
    assert len(buttons) >= 3  # list entries, save/create, discard: the scan saw the controls
    assert [b for b in buttons + labels if FORBIDDEN.search(b)] == []

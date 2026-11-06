"""S-XCT-23 - a method no route serves is answered 405 in the product envelope, by one global handler.

Every clause: POST /health/live, the single handler registration, 404 vs 405 separability, the same 405
body on DELETE at the four admin entity paths and the four lookup vocabulary paths (with no DELETE route
mounted on any of them), DELETE /api/admin/seats/{seat_id} answering 204 for a hall with no showtime
rows, POST/PUT/PATCH/DELETE on /api/reports/dashboard, and METHOD_NOT_ALLOWED on exactly one line of
the generated contract.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import load_settings
from app.main import create_app
from tests.adm.kit import make_category, make_cinema, make_lookup, make_screen, make_seat, new_film, sign_in
from tests.dbkit import BACKEND_DIR, app_settings, owner_sql
from tests.xct._support import REPO, mounted_routes
from tests.test_health import ok_probe

BODY_MESSAGE = "That action is not available. Nothing was changed."


@pytest.fixture
def client(valid_env, clock):
    with TestClient(create_app(load_settings(), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])) as c:
        yield c


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_non_get_method_on_health_live_is_405_in_the_envelope(client, method):
    r = client.request(method, "/health/live")
    assert r.status_code == 405
    err = r.json()["error"]
    assert (err["code"], err["message"], err["details"]) == ("METHOD_NOT_ALLOWED", BODY_MESSAGE, {})
    assert re.fullmatch(r"[0-9a-f]{8}", err["request_id"])
    assert "GET" in r.headers["allow"]


def test_an_unknown_address_is_404_not_found_not_405(client):
    r = client.get("/api/nothing-here")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["message"] == "That page does not exist."


def test_the_handler_is_registered_exactly_once_on_the_application():
    hits = [
        f"{p.relative_to(BACKEND_DIR)}:{i}"
        for p in (BACKEND_DIR / "app").rglob("*.py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "method_not_allowed" in line
    ]
    assert hits == ["app/api/errors.py:" + hits[0].split(":")[1]] and len(hits) == 1


def test_the_405_body_is_identical_whatever_was_addressed(client):
    bodies = set()
    for method, path in [("POST", "/health/live"), ("DELETE", "/health/ready"), ("PUT", "/health/live")]:
        err = client.request(method, path).json()["error"]
        err.pop("request_id")
        bodies.add(json.dumps(err, sort_keys=True))
    assert len(bodies) == 1


@pytest.fixture
def admin_client(migrated_db, clock):
    """tests/adm/kit.py's client: the real app on this module's migrated database."""
    app = create_app(app_settings(migrated_db), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(app, raise_server_exceptions=False) as c:
        c.clock, c.db = clock, migrated_db
        yield c


KINDS = ("language", "certification", "genre", "format")


def _same_405(r) -> dict:
    assert r.status_code == 405, (r.request.method, r.request.url, r.text)
    err = dict(r.json()["error"])
    assert (err["code"], err["message"]) == ("METHOD_NOT_ALLOWED", BODY_MESSAGE)
    assert re.fullmatch(r"[0-9a-f]{8}", err.pop("request_id"))
    return err


def test_delete_on_the_admin_entities_and_the_four_vocabularies_is_the_same_405(admin_client):
    c = admin_client
    sign_in(c)
    cinema = make_cinema(c.db)
    hall = make_screen(c.db, cinema)
    film = new_film(c)["id"]
    paths = [f"/api/admin/movies/{film}", "/api/admin/showtimes/41", f"/api/admin/screens/{hall}", f"/api/admin/cinemas/{cinema}"]
    for kind in KINDS:
        paths += [f"/api/admin/lookups/{kind}", f"/api/admin/lookups/{kind}/{make_lookup(c.db, kind)}"]
    bodies = [_same_405(c.delete(p)) for p in paths]
    assert len(bodies) == 12 and all(b == bodies[0] for b in bodies)
    templates = ("/api/admin/movies/{movie_id}", "/api/admin/showtimes/{showtime_id}", "/api/admin/screens/{screen_id}",
                 "/api/admin/cinemas/{cinema_id}", "/api/admin/lookups/{kind}", "/api/admin/lookups/{kind}/{id}")
    assert [(m, p) for m, p in mounted_routes(c.app) if m == "DELETE" and p in templates] == []


def test_delete_on_a_seat_in_a_hall_with_no_showtimes_is_a_real_204(admin_client):
    c = admin_client
    sign_in(c)
    hall = make_screen(c.db, make_cinema(c.db))
    seat = make_seat(c.db, hall, "A1", make_category(c.db))
    assert owner_sql(c.db, "SELECT count(*) FROM showtime WHERE screen_id = %s", (hall,)) == [(0,)]
    assert ("DELETE", "/api/admin/seats/{seat_id}") in mounted_routes(c.app)
    r = c.delete(f"/api/admin/seats/{seat}")
    assert r.status_code == 204, r.text
    assert owner_sql(c.db, "SELECT count(*) FROM seat WHERE id = %s", (seat,)) == [(0,)]


def test_every_other_verb_on_the_dashboard_is_the_same_405(admin_client):
    c = admin_client
    sign_in(c)
    bodies = [_same_405(c.request(m, "/api/reports/dashboard")) for m in ("POST", "PUT", "PATCH", "DELETE")]
    assert all(b == bodies[0] for b in bodies)


def test_the_contract_carries_method_not_allowed_on_one_line():
    text = (REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8")
    assert len([ln for ln in text.splitlines() if "METHOD_NOT_ALLOWED" in ln]) == 1

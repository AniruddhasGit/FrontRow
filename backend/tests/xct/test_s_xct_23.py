"""S-XCT-23 - a method no route serves is answered 405 in the product envelope, by one global handler.

Covered: POST /health/live, the single handler registration, 404 vs 405 separability, and the same
405 body for every verb on a path that exists for GET. NOT covered yet: the admin entity paths and
/api/reports/dashboard (other lanes' routes), and DELETE /api/admin/seats/{seat_id} (EP-ADM-21).
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import load_settings
from app.main import create_app
from tests.dbkit import BACKEND_DIR
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

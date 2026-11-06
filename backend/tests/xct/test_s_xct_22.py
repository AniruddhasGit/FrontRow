"""S-XCT-22 (P-XCT-11): one error envelope on every route, a stable code, and the request id rendered on 5xx only.

The sweep forces one failure on every mounted route - a wrong method where one exists (405), else the request as a
guest with an unparseable path id (401 / 404 / 422 by the route's own order) - and validates every captured body against
the envelope with no additional property. Request ids are read from each response, never compared to a literal.

NOT asserted here (the row stays Blocked on them): the interface clauses - a 4xx page not displaying the request id while
a 5xx page shows the eight characters, and five separate interface tests for the five 409 codes - which belong to the
frontend feature lanes' render tests.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from tests.pay.kit import api, clock_at, world7
from tests.xct._support import rg

pytestmark = pytest.mark.anyio

RID = re.compile(r"^[0-9a-f]{8}$")
LEAK = re.compile(r"(Traceback|File \"|SELECT |INSERT |psycopg|sqlalchemy|booking_seat|\.rds\.amazonaws\.com)")
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _valid_envelope(body: dict, response) -> None:
    assert set(body) == {"error"}, body
    error = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}, error
    assert isinstance(error["code"], str) and error["code"].isupper()
    assert isinstance(error["message"], str) and isinstance(error["details"], dict)
    assert RID.match(error["request_id"]) and response.headers["x-request-id"] == error["request_id"]


async def test_a_forced_failure_on_every_mounted_route_is_the_envelope_and_leaks_nothing(migrated_db):
    world7(migrated_db)
    async with api(migrated_db, clock_at()) as c:
        routes = [r for r in c.application.routes if isinstance(r, APIRoute)]
        captured = []
        for route in routes:
            path = re.sub(r"\{[^}]+\}", "zz", route.path)
            other = [m for m in METHODS if m not in route.methods]
            method = other[0] if other and not any(
                isinstance(r, APIRoute) and r.path == route.path and other[0] in r.methods for r in routes) else sorted(route.methods)[0]
            r = await c.request(method, path, content=b"{}", headers={"Content-Type": "application/json"})
            if r.status_code < 400:
                continue  # a public route that answers a guest and takes no id (e.g. /health/live) has nothing to force
            captured.append((method, route.path, r.status_code))
            _valid_envelope(r.json(), r)
            assert not LEAK.search(r.text), (route.path, r.text)
    assert len(captured) >= len(routes) // 2, captured  # the sweep reached most of the table, not a handful


async def test_unknown_path_validation_and_unhandled_exception(migrated_db, monkeypatch):
    world7(migrated_db)
    async with api(migrated_db, clock_at()) as c:
        missing = await c.get("/api/no-such-thing")
        invalid = await c.post("/api/auth/register", json={"email": "", "password": "x"})

        async def boom(*args, **kwargs):
            raise RuntimeError("an unhandled failure with a secret-looking SELECT inside")

        from app.domain import accounts

        monkeypatch.setattr(accounts, "register", boom)
        crashed = await c.post("/api/auth/register", json={"email": "crash@example.com", "password": "correct horse battery"})
    assert (missing.status_code, missing.json()["error"]["code"], missing.json()["error"]["message"]) == (
        404, "NOT_FOUND", "That page does not exist.")
    assert (invalid.status_code, invalid.json()["error"]["code"]) == (422, "VALIDATION_FAILED")
    assert invalid.json()["error"]["details"]["field"] == "email"
    rid = crashed.json()["error"]["request_id"]
    assert crashed.status_code == 500 and crashed.json()["error"]["code"] == "INTERNAL_ERROR"
    assert crashed.json()["error"]["message"] == f"The server could not complete this request. If you need help, quote {rid}."
    assert not LEAK.search(crashed.text)
    for r in (missing, invalid, crashed):
        _valid_envelope(r.json(), r)


def test_the_interface_branches_on_code_never_on_message():
    assert rg(r"\.message\s*===|\.message\s*==|message\.includes\(", "frontend/src") == []

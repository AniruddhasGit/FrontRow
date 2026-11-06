"""S-RPT-03 - role and screen scope resolved once, on the reports router (P-RPT-02).

Not asserted: 'as a guest returns 403'. A guest is the ABSENCE of a session (app/domain/accounts Role.GUEST, and
users.role's CHECK admits no 'guest'), so a guest's request is the unauthenticated one: 401, asserted below."""

from __future__ import annotations

import inspect

import pytest

from app.api import reports
from app.api.deps import report_scope
from tests.adm.kit import routes
from tests.rpt.kit import client, film, get, owner_sql, show, strip_rid, user_row, assign, venue  # noqa: F401

D = "/api/reports/dashboard?period=day"


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {i: 10 for i in range(1, 7)})
    m = film(w, "DEMO MOVIE 01")
    show(w, 105, 5, m, "2026-08-14T10:00:00Z")
    w["admin"], w["M"], w["customer"] = user_row(migrated_db, "admin"), user_row(migrated_db, "manager"), user_row(migrated_db, "customer")
    assign(migrated_db, w["M"], 3, 5)
    return w


def test_the_router_carries_the_role_dependency_then_report_scope():
    assert [d.dependency.__name__ for d in reports.router.dependencies] == ["require_role_admin_manager", "report_scope"]


def test_no_handler_declares_screen_id_only_report_scope_does(client):
    found = [r for r in routes(client.app) if r.path.startswith("/api/reports/") and r.path != "/api/reports/audit"]
    assert {r.path for r in found} == {"/api/reports/dashboard", "/api/reports/showtimes", "/api/reports/scope"}

    def callables(dependant):
        out = [dependant.call] if dependant.call else []
        for d in dependant.dependencies:
            out += callables(d)
        return out

    for route in found:
        assert "screen_id" not in inspect.signature(route.endpoint).parameters, route.path
        declaring = {c for c in callables(route.dependant) if "screen_id" in inspect.signature(c).parameters}
        assert declaring == {report_scope}, route.path


def test_401_and_403_by_role(client, world):
    r = get(client, None, D)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (401, "AUTH_REQUIRED", "Sign in to see the dashboard.")
    r = get(client, world["customer"], D)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (403, "FORBIDDEN", "This page is for managers and administrators.")


def test_admin_sees_every_screen_manager_sees_their_own(client, world):
    assert get(client, world["admin"], D).json()["screen_ids"] == [1, 2, 3, 4, 5, 6]
    assert get(client, world["M"], D).json()["screen_ids"] == [3, 5]
    assert get(client, world["M"], D + "&screen_id=3").json()["screen_ids"] == [3]


def test_a_foreign_and_a_missing_hall_answer_the_same_403_to_a_manager(client, world):
    a, b = get(client, world["M"], D + "&screen_id=1"), get(client, world["M"], D + "&screen_id=9")
    assert a.status_code == b.status_code == 403
    assert a.json()["error"]["message"] == "That hall is not assigned to this account."
    assert strip_rid(a.json()) == strip_rid(b.json())
    r = get(client, world["admin"], D + "&screen_id=9")
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (404, "NOT_FOUND", "That hall does not exist.")
    r = get(client, world["M"], D + "&screen_id=abc")
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")


def test_an_out_of_service_hall_is_still_a_valid_narrowing_value(client, world):
    before = get(client, world["M"], D + "&screen_id=5").json()
    assert before["shows"] == 1  # not vacuous: the hall has a showtime in the period
    owner_sql(world["db"], "UPDATE screen SET is_active = false WHERE id = 5")
    try:
        after = get(client, world["M"], D + "&screen_id=5").json()
    finally:
        owner_sql(world["db"], "UPDATE screen SET is_active = true WHERE id = 5")
    before.pop("evaluated_at_utc"), after.pop("evaluated_at_utc")
    assert after == before

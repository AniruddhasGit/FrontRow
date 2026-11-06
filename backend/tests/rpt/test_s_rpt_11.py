"""S-RPT-11 - EP-RPT-03 returns exactly what the router dependency resolved; one insert moves all three endpoints."""

from __future__ import annotations

import pytest

from tests.rpt.kit import assign, client, get, one, owner_sql, prd_world, sell, show  # noqa: F401

DASH = "/api/reports/dashboard?period=day&date=2026-08-14"
SHOWS = "/api/reports/showtimes?period=day&date=2026-08-14&limit=50&offset=0"


@pytest.fixture(scope="module")
def world(migrated_db):
    w = prd_world(migrated_db)
    owner_sql(migrated_db, "UPDATE screen SET is_active = false WHERE id = 6")  # an out-of-service hall stays listed
    st = show(w, None, 4, 2, "2026-08-14T09:00:00Z")
    sell(w, st, 2, 25000)
    return w


def test_a_manager_reads_their_halls_and_today_from_the_injected_clock(client, world):
    body = get(client, world["M"], "/api/reports/scope").json()
    assert {k: body[k] for k in ("role", "scope_empty", "all_halls", "timezone", "today")} == {
        "role": "manager", "scope_empty": False, "all_halls": False, "timezone": "Asia/Kolkata", "today": "2026-08-14"}
    assert body["screens"] == [{"screen_id": 3, "screen_name": "Hall 3", "is_active": True},
                               {"screen_id": 5, "screen_name": "Hall 5", "is_active": True}]


def test_the_admin_reads_every_hall_including_one_out_of_service(client, world):
    body = get(client, world["admin"], "/api/reports/scope").json()
    assert [s["screen_id"] for s in body["screens"]] == [1, 2, 3, 4, 5, 6] and body["all_halls"] is True
    assert {s["screen_id"]: s["is_active"] for s in body["screens"]}[6] is False


def test_unassigned_customer_and_unauthenticated(client, world):
    body = get(client, world["P"], "/api/reports/scope").json()
    assert (body["scope_empty"], body["screens"]) == (True, [])
    r = get(client, world["customer"], "/api/reports/scope")
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (403, "FORBIDDEN", "This page is for managers and administrators.")
    r = get(client, None, "/api/reports/scope")
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (401, "AUTH_REQUIRED", "Sign in to see the dashboard.")


def test_one_assignment_moves_all_three_endpoints(client, world):
    total_before = get(client, world["M"], SHOWS).json()["total"]
    assign(world["db"], world["M"], 4)
    added = one(world["db"], "SELECT count(*) FROM showtime WHERE screen_id=4 AND starts_at >= '2026-08-13T18:30:00Z' "
                             "AND starts_at < '2026-08-14T18:30:00Z'")
    assert added > 0  # not vacuous
    assert [s["screen_id"] for s in get(client, world["M"], "/api/reports/scope").json()["screens"]] == [3, 4, 5]
    assert get(client, world["M"], DASH).json()["screen_ids"] == [3, 4, 5]
    assert get(client, world["M"], SHOWS).json()["total"] == total_before + added

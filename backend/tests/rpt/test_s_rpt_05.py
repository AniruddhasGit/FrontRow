"""S-RPT-05 - an empty scope short-circuits (no aggregate runs) and the three zeros stay three facts (P-RPT-08)."""

from __future__ import annotations

import pytest

from tests.rpt.kit import ServerLog, assign, film, get, make_client, sell, show, user_row, venue

MONTH = "/api/reports/dashboard?period=month&date=2026-08-14"


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {1: 30, 2: 30})
    m = film(w, "DEMO MOVIE 01")
    show(w, 301, 1, m, "2026-08-14T14:00:00Z")
    sell(w, 301, 5, 25000)
    show(w, 302, 2, m, "2026-08-20T14:00:00Z")  # Q's hall: scheduled, nothing sold
    w["admin"], w["P"], w["Q"] = user_row(migrated_db, "admin"), user_row(migrated_db, "manager"), user_row(migrated_db, "manager")
    assign(migrated_db, w["Q"], 2)
    return w


def test_an_unassigned_manager_gets_200_and_no_aggregate_runs(world):
    log = ServerLog(world["db"])
    with make_client(world["db"]) as c:
        log.attach(c)
        log.lines.clear()
        r = get(c, world["P"], MONTH)
        statements = log.statements()
        admin = get(c, world["admin"], MONTH).json()
    assert r.status_code == 200
    body = r.json()
    assert {k: body[k] for k in ("scope_empty", "screen_ids", "shows", "seats_sold", "capacity", "takings_paise",
                                 "occupancy_pct", "films")} == {
        "scope_empty": True, "screen_ids": [], "shows": 0, "seats_sold": 0, "capacity": 0, "takings_paise": 0,
        "occupancy_pct": None, "films": []}
    assert statements, "the server log captured nothing - the check would pass vacuously"
    assert [s for s in statements if "booking_seat" in s or "SUM(" in s] == []
    assert admin["takings_paise"] > 0 and body["takings_paise"] != admin["takings_paise"]


def test_the_three_zero_states_differ(world):
    with make_client(world["db"]) as c:
        listing = get(c, world["P"], "/api/reports/showtimes?period=month&date=2026-08-14")
        none = get(c, world["P"], MONTH).json()
        unsold = get(c, world["Q"], MONTH).json()
        empty_day = get(c, world["Q"], "/api/reports/dashboard?period=day&date=2026-08-14").json()
    assert listing.status_code == 200 and (listing.json()["total"], listing.json()["rows"]) == (0, [])
    assert (unsold["scope_empty"], unsold["takings_paise"], unsold["occupancy_pct"]) == (False, 0, 0.0) and unsold["capacity"] > 0
    assert (empty_day["scope_empty"], empty_day["capacity"], empty_day["occupancy_pct"]) == (False, 0, None)
    pairs = {(b["scope_empty"], b["occupancy_pct"]) for b in (none, unsold, empty_day)}
    assert len(pairs) == 3

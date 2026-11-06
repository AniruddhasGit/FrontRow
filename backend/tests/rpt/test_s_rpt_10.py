"""S-RPT-10 - the paginated per-show listing on its own endpoint (P-RPT-06)."""

from __future__ import annotations

import pytest

from tests.rpt.kit import assign, client, get, one, prd_world, show, user_row  # noqa: F401

URL = "/api/reports/showtimes?period=day&date=2026-08-14"


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def _check(db, row):
    j = ("FROM booking_seat bs JOIN booking b ON bs.booking_id=b.id JOIN payment p ON p.id=b.payment_id "
         "WHERE b.showtime_id = %s AND b.status='confirmed' AND p.state='captured'")
    assert row["takings_paise"] == one(db, f"SELECT COALESCE(SUM(bs.price_paise),0) {j}", (row["showtime_id"],))
    assert row["seats_sold"] == one(db, f"SELECT count(*) {j}", (row["showtime_id"],))


def test_the_worked_example(client, world):
    body = get(client, world["M"], URL + "&limit=50&offset=0").json()
    assert body["total"] == 2 and (body["limit"], body["offset"]) == (50, 0)
    a, b = body["rows"]
    assert a == {"showtime_id": 101, "starts_at": "2026-08-14T19:30:00+05:30", "screen_id": 3, "screen_name": "Hall 3",
                 "movie_id": 1, "title": "DEMO MOVIE 01", "seats_sold": 97, "capacity": 150, "occupancy_pct": 64.7,
                 "takings_paise": 2483331, "has_started": False}
    assert (a["occupancy_pct"], b["occupancy_pct"]) == ((97 * 2000 + 150) // 300 / 10, (12 * 2000 + 220) // 440 / 10)
    assert {k: b[k] for k in ("showtime_id", "starts_at", "screen_id", "screen_name", "seats_sold", "capacity",
                              "occupancy_pct", "takings_paise", "has_started")} == {
        "showtime_id": 102, "starts_at": "2026-08-14T23:45:00+05:30", "screen_id": 5, "screen_name": "Hall 5",
        "seats_sold": 12, "capacity": 220, "occupancy_pct": 5.5, "takings_paise": 300000, "has_started": False}
    for row in (a, b):
        _check(world["db"], row)
    assert get(client, world["M"], URL).json() == body  # limit and offset default to 50 and 0


@pytest.mark.parametrize("query, message", [("&limit=0", "Ask for between 1 and 200 rows."),
                                             ("&limit=201", "Ask for between 1 and 200 rows."),
                                             ("&offset=-1", "The row offset cannot be negative.")])
def test_bounds(client, world, query, message):
    r = get(client, world["M"], URL + query)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (422, "VALIDATION_FAILED", message)


def test_no_sort_parameter_is_declared_or_honoured(client, world):
    spec = client.app.openapi()["paths"]["/api/reports/showtimes"]["get"]
    names = {p["name"] for p in spec.get("parameters", [])}
    assert "period" in names and not names & {"sort", "order"}
    assert get(client, world["M"], URL + "&sort=takings_paise").content == get(client, world["M"], URL).content


def test_has_started_comes_from_the_injected_clock(client, world):
    show(world, 100, 3, 1, "2026-08-14T06:00:00Z")  # 11:30 local, before the clock's 12:50Z
    rows = get(client, world["M"], URL).json()
    assert rows["total"] == 3
    started = {r["showtime_id"]: r["has_started"] for r in rows["rows"]}
    assert started == {100: True, 101: False, 102: False}
    assert all(r["takings_paise"] > 0 for r in rows["rows"] if r["showtime_id"] in (101, 102))


def test_total_counts_the_period_not_the_page(client, world):
    six = user_row(world["db"], "manager")
    assign(world["db"], six, 6)
    for i in range(214):
        show(world, None, 6, 2, f"2026-08-14T{i % 18:02d}:{i // 18:02d}:00Z")
    body = get(client, six, URL).json()
    assert (body["total"], len(body["rows"])) == (214, 50)

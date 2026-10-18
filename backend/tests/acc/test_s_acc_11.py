"""S-ACC-11 (P-ACC-10, EP-ACC-07): the caller's own bookings in two groups, both arrays always present."""

from __future__ import annotations

import re

import pytest

from tests.pay.kit import add_seats, api, book, clock_at, cookies, movie_and_showtime, user, world7

pytestmark = pytest.mark.anyio
REF = r"^FR-[23456789ACDEFHJKMNPQRTVWXY]{4}-[23456789ACDEFHJKMNPQRTVWXY]{4}$"
KEYS = {"reference", "movie_title", "hall_name", "seat_count", "group", "showtime_starts_at", "showtime_ends_at", "booked_at",
        "seats", "total_paise"}
NOW = "2026-08-14T14:00:00+00:00"


@pytest.fixture
def world(migrated_db):
    w = world7(migrated_db)
    db = migrated_db
    movie_and_showtime(db, w, 70, "2026-08-10T20:00:00+05:30")  # past at NOW
    add_seats(db, w["screen"], w["standard"], [(2000 + n, "K", n) for n in range(1, 41)] + [(420, "F", 2), (421, "F", 10)], [7, 70])
    return w


async def test_two_upcoming_and_thirty_seven_past_page_independently(world):
    db = world["db"]
    u = user(db)
    for n in (1, 2):
        book(db, u, 7, [2000 + n])
    for n in range(1, 38):
        book(db, u, 70, [2000 + n])
    async with api(db, clock_at(NOW)) as c:
        got = {}
        for page in (1, 2, 3):
            r = await c.get(f"/api/me/bookings?page={page}&page_size=20", cookies=cookies(c, u))
            assert r.status_code == 200, r.text
            body = r.json()
            assert {"upcoming", "past", "page", "page_size", "total_upcoming", "total_past"} <= set(body)
            assert (body["total_upcoming"], body["total_past"], body["page"], body["page_size"]) == (2, 37, page, 20)
            got[page] = (len(body["upcoming"]), len(body["past"]))
        assert got == {1: (2, 20), 2: (0, 17), 3: (0, 0)}
        only = (await c.get("/api/me/bookings?group=upcoming", cookies=cookies(c, u))).json()
        assert only["past"] == [] and only["total_past"] == 37 and len(only["upcoming"]) == 2


async def test_each_row_carries_exactly_the_published_keys_and_the_cinemas_offset(world):
    db = world["db"]
    u = user(db)
    book(db, u, 7, [420, 421], created_at="2026-08-14T13:00:00Z")  # F2 and F10
    book(db, u, 7, [404, 402, 403], created_at="2026-08-14T13:30:00Z", prices=[45000, 54000, 54000])  # F9, F7, F8 in that order
    async with api(db, clock_at(NOW)) as c:
        rows = (await c.get("/api/me/bookings", cookies=cookies(c, u))).json()["upcoming"]
    assert len(rows) == 2
    for row in rows:
        assert set(row) == KEYS
        assert re.match(REF, row["reference"]) and isinstance(row["seat_count"], int) and 1 <= row["seat_count"] <= 10
        assert row["showtime_starts_at"] == "2026-08-14T20:00:00+05:30" and row["showtime_ends_at"] == "2026-08-14T22:00:00+05:30"
        assert row["booked_at"].endswith("+05:30") and row["group"] == "upcoming"
    by_count = {r["seat_count"]: r for r in rows}
    assert by_count[2]["seats"] == ["F2", "F10"]
    assert by_count[3]["seats"] == ["F7", "F8", "F9"]
    assert by_count[3]["total_paise"] == 153000 and type(by_count[3]["total_paise"]) is int
    assert by_count[2]["booked_at"] == "2026-08-14T18:30:00+05:30"


@pytest.mark.parametrize("query", ["page=0", "page=1001", "page_size=0", "page_size=51", "group=other"])
async def test_out_of_bounds_parameters_are_422(world, query):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at(NOW)) as c:
        r = await c.get(f"/api/me/bookings?{query}", cookies=cookies(c, u))
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_no_session_is_401_and_no_bookings_is_two_empty_arrays(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at(NOW)) as c:
        r = await c.get("/api/me/bookings")
        assert r.status_code == 401 and r.json()["error"]["message"] == "Sign in to see your bookings."
        empty = (await c.get("/api/me/bookings", cookies=cookies(c, u))).json()
    assert (empty["upcoming"], empty["past"], empty["total_upcoming"], empty["total_past"]) == ([], [], 0, 0)

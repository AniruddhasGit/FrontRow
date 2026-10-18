"""S-BRW-09 (P-BRW-06): next_date_with_showtimes - strictly after, inside the window, still open, matching the
filters - all four met by ONE showtime.

Not here (browser harness): the rendered 'Next: Sun 16 Aug' button and 'No showtimes for this movie.'. The
label form itself is unit-tested in frontend/src/features/browse.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.domain.browse.catalogue import ShowtimeFilters, next_date_statement
from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_lookup, make_movie, make_screen,
                           make_seat, make_showtime, reset_catalogue)

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_screen(db, make_cinema(db))
    make_seat(db, hall, "A", 1, 1, 1, make_category(db))
    f2d, f3d = make_lookup(db, "format", "2D"), make_lookup(db, "format", "3D")
    film = make_movie(db, display_until="2026-08-21T00:00:00+05:30")
    first = make_showtime(db, film, hall, "2026-08-15T19:30:00+05:30", format_id=f2d)
    make_showtime(db, film, hall, "2026-08-16T11:00:00+05:30", format_id=f3d)
    make_showtime(db, film, hall, "2026-08-17T09:00:00+05:30", format_id=f2d)
    return {"db": db, "film": film, "first": first, "2d": f2d}


async def _get(world, clock_at: str, **params):
    clock = SetClock()
    clock.set(clock_at)
    async with api(world["db"], clock, SALES_CUTOFF_MINUTES="15") as c:
        r = await c.get("/api/showtimes", params={"movie_id": world["film"], **params})
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_closed_day_is_listed_not_emptied_and_names_the_next_open_date(world):
    body = await _get(world, "2026-08-15T21:00:00+05:30", date="2026-08-15")
    assert [(s["id"], s["sales_closed"]) for s in body["showtimes"]] == [(world["first"], True)]
    assert body["next_date_with_showtimes"] == "2026-08-16"


async def test_the_filters_are_part_of_the_test(world):
    body = await _get(world, "2026-08-15T21:00:00+05:30", date="2026-08-15", format_id=world["2d"])
    assert body["next_date_with_showtimes"] == "2026-08-17"


async def test_nothing_further_is_null(world):
    body = await _get(world, "2026-08-15T21:00:00+05:30", date="2026-08-17")
    assert body["next_date_with_showtimes"] is None


async def test_the_requested_date_is_excluded_even_while_it_is_open(world):
    body = await _get(world, "2026-08-15T10:00:00+05:30", date="2026-08-15")
    assert [s["sales_closed"] for s in body["showtimes"]] == [False]
    assert body["next_date_with_showtimes"] == "2026-08-16"


def test_the_search_is_bounded_by_display_until():
    until = datetime.fromisoformat("2026-08-21T00:00:00+05:30")
    film = {"id": 1, "display_from": datetime.fromisoformat("2026-08-14T00:00:00+05:30"), "display_until": until}
    stmt = next_date_statement(film, date(2026, 8, 19), ShowtimeFilters(), datetime.fromisoformat("2026-08-15T21:00:00+05:30"),
                               timedelta(minutes=15), {1: "Asia/Kolkata"})
    compiled = stmt.compile()
    assert "showtime.starts_at <" in str(compiled)
    assert until in compiled.params.values()

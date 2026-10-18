"""S-BRW-08 (P-BRW-06, EP-BRW-04): every showtime of a film on a local date, in the cinema's offset.

Not here (browser harness): the rendered 'That movie is not showing.' with its 'Back to what is showing'
link, and the rendered 'No showtimes on this date.'.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_lookup, make_movie, make_screen,
                           make_seat, make_showtime, reset_catalogue)

pytestmark = pytest.mark.anyio

KEYS = {"id", "starts_at", "ends_at", "sales_close_at", "sales_closed", "screen", "cinema", "format", "base_price_paise"}


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    cinema = make_cinema(db)
    h1, h2 = make_screen(db, cinema, "Hall 1"), make_screen(db, cinema, "Hall 2")
    cat = make_category(db)
    make_seat(db, h1, "A", 1, 1, 1, cat)
    make_seat(db, h2, "A", 1, 1, 1, cat)
    fmt = make_lookup(db, "format")
    film = make_movie(db, runtime=125)
    late = make_showtime(db, film, h2, "2026-08-15T19:30:00+05:30", "2026-08-15T21:50:00+05:30", price=24999)
    noon = make_showtime(db, film, h1, "2026-08-15T14:30:00+05:30", format_id=fmt)
    morning = make_showtime(db, film, h2, "2026-08-15T11:00:00+05:30")
    return {"db": db, "film": film, "order": [morning, noon, late], "late": late, "fmt": fmt}


async def test_three_showtimes_in_start_order_with_exactly_the_published_fields(world):
    clock = SetClock()
    clock.set("2026-08-15T09:00:00+05:30")
    async with api(world["db"], clock) as c:
        r = await c.get("/api/showtimes", params={"movie_id": world["film"], "date": "2026-08-15"})
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2026-08-15"
    assert [s["id"] for s in body["showtimes"]] == world["order"]
    for s in body["showtimes"]:
        assert set(s) == KEYS
        assert set(s["screen"]) == {"id", "name"} and set(s["cinema"]) == {"id", "name"}
        assert s["format"] is None or set(s["format"]) == {"id", "name"}
        assert type(s["base_price_paise"]) is int
    instants = re.findall(r'"(\d{4}-\d\d-\d\dT[^"]+)"', r.text)
    assert instants and all(i.endswith("+05:30") for i in instants) and not any(i.endswith("Z") for i in instants)
    late = next(s for s in body["showtimes"] if s["id"] == world["late"])
    assert late["ends_at"] == "2026-08-15T21:50:00+05:30"  # stored, not 19:30 + 125 minutes = 21:35
    assert late["base_price_paise"] == 24999


async def test_with_no_date_today_is_the_cinemas_today_not_the_servers(world):
    clock = SetClock()
    clock.set(datetime(2026, 8, 14, 19, 5, tzinfo=timezone.utc))  # 2026-08-15T00:35:00+05:30
    async with api(world["db"], clock) as c:
        r = await c.get("/api/showtimes", params={"movie_id": world["film"]})
    assert r.json()["date"] == "2026-08-15"
    assert [s["id"] for s in r.json()["showtimes"]] == world["order"]


@pytest.mark.parametrize("column,value", [("published_at", None), ("display_until", "2026-08-15T00:00:00+05:30")])
async def test_a_film_failing_either_gate_is_404(world, column, value):
    film = make_movie(world["db"], **{column: value})
    clock = SetClock()
    clock.set("2026-08-15T09:00:00+05:30")
    async with api(world["db"], clock) as c:
        r = await c.get("/api/showtimes", params={"movie_id": film, "date": "2026-08-15"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND" and r.json()["error"]["message"] == "That movie is not showing."


async def test_a_malformed_date_is_422_and_an_empty_date_is_an_empty_200(world):
    clock = SetClock()
    clock.set("2026-08-15T09:00:00+05:30")
    async with api(world["db"], clock) as c:
        bad = await c.get("/api/showtimes", params={"movie_id": world["film"], "date": "2026-8-15"})
        empty = await c.get("/api/showtimes", params={"movie_id": world["film"], "date": "2026-08-16"})
    assert bad.status_code == 422 and bad.json()["error"]["message"] == "That date is not valid."
    assert empty.status_code == 200 and empty.json()["showtimes"] == []

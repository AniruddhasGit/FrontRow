"""S-BRW-01 (P-BRW-01): every movie-addressed read is gated on publication AND the display window, in SQL.

The poster, the showtime and the seat map are the three ungated endpoints: each answers for the film at the exclusive
bound. The API's message for the excluded film's 404 is asserted here; the rendered copy 'That movie is not showing.'
is asserted in frontend/src/features/browse/render.test.mjs.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import async_url
from app.domain.browse.catalogue import ListingFilters, listing_statement
from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_movie, make_screen, make_seat,
                           make_showtime, reset_catalogue, settings_for, without_request_id)

pytestmark = pytest.mark.anyio

INSTANTS = {
    "2026-08-13T23:59:59+05:30": False,
    "2026-08-14T00:00:00+05:30": True,
    "2026-08-20T23:59:59+05:30": True,
    "2026-08-21T00:00:00+05:30": False,
}


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    cinema = make_cinema(migrated_db)
    screen = make_screen(migrated_db, cinema)
    make_seat(migrated_db, screen, "A", 1, 1, 1, make_category(migrated_db))
    return {"db": migrated_db, "cinema": cinema, "screen": screen}


async def _listed_ids(c, clock, instant) -> list[int]:
    clock.set(instant)
    r = await c.get("/api/movies")
    assert r.status_code == 200
    return [m["id"] for m in r.json()["movies"]]


async def test_listing_follows_the_window_inclusive_from_exclusive_until(world):
    film = make_movie(world["db"])
    clock = SetClock()
    async with api(world["db"], clock) as c:
        for instant, shown in INSTANTS.items():
            assert (film in await _listed_ids(c, clock, instant)) is shown, instant


@pytest.mark.parametrize("column", ["published_at", "display_from", "display_until"])
async def test_a_null_gate_column_hides_the_film_at_every_instant(world, column):
    film = make_movie(world["db"], **{column: None})
    clock = SetClock()
    async with api(world["db"], clock) as c:
        for instant in INSTANTS:
            assert film not in await _listed_ids(c, clock, instant), instant


def test_the_gate_is_sql_with_no_coalesce():
    stmt = listing_statement(datetime.fromisoformat("2026-08-21T00:00:00+05:30"), ListingFilters(), {1: "Asia/Kolkata"})
    text = str(stmt.compile())
    assert "COALESCE" not in text.upper()
    for fragment in ("published_at IS NOT NULL", "display_from <=", "display_until >"):
        assert fragment in text


async def test_executing_the_statement_at_the_exclusive_bound_returns_no_rows(world):
    make_movie(world["db"])
    engine = create_async_engine(async_url(settings_for(world["db"]).DATABASE_URL))
    try:
        async with engine.connect() as conn:
            at_bound = datetime.fromisoformat("2026-08-21T00:00:00+05:30")
            inside = datetime.fromisoformat("2026-08-20T23:59:59+05:30")
            assert (await conn.execute(listing_statement(at_bound, ListingFilters(), {}))).all() == []
            assert len((await conn.execute(listing_statement(inside, ListingFilters(), {}))).all()) == 1
    finally:
        await engine.dispose()


async def test_an_excluded_film_is_indistinguishable_from_one_that_never_existed(world):
    film = make_movie(world["db"])
    clock = SetClock()
    clock.set("2026-08-21T00:00:00+05:30")
    async with api(world["db"], clock) as c:
        excluded = await c.get(f"/api/movies/{film}")
        never = await c.get("/api/movies/999999")
        shown_later = None
        clock.set("2026-08-15T12:00:00+05:30")
        shown_later = await c.get(f"/api/movies/{film}")
    assert excluded.status_code == never.status_code == 404
    a, b = excluded.json(), never.json()
    assert a["error"]["code"] == "NOT_FOUND"
    assert a["error"]["message"] == "That movie is not showing."
    assert without_request_id(a) == without_request_id(b)
    assert set(a["error"]) == set(b["error"])
    assert a["error"]["request_id"] and b["error"]["request_id"] and a["error"]["request_id"] != b["error"]["request_id"]
    assert shown_later.status_code == 200 and shown_later.json()["id"] == film


@pytest.mark.parametrize("bad", ["0", "abc"])
async def test_a_bad_movie_id_is_422_before_any_statement(world, bad):
    async with api(world["db"], SetClock()) as c:
        c.statements.reset()
        r = await c.get(f"/api/movies/{bad}")
        assert c.statements.statements == []
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_poster_showtime_and_seatmap_are_ungated_at_the_exclusive_bound(world):
    film = make_movie(world["db"], poster_key="posters/1/" + "c" * 32)
    st = make_showtime(world["db"], film, world["screen"], "2026-08-20T19:30:00+05:30")
    clock = SetClock()
    clock.set("2026-08-21T00:00:00+05:30")
    async with api(world["db"], clock) as c:
        poster = await c.get(f"/api/movies/{film}/poster")
        header = await c.get(f"/api/showtimes/{st}")
        seatmap = await c.get(f"/api/showtimes/{st}/seatmap")
        listing = await c.get("/api/showtimes", params={"movie_id": film, "date": "2026-08-20"})
    assert poster.status_code == 302 and "X-Amz-Signature=" in poster.headers["location"]
    assert header.status_code == 200 and seatmap.status_code == 200
    assert listing.status_code == 404  # the showtime LIST is movie-addressed and gated

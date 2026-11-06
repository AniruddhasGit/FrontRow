"""S-BRW-04 (P-BRW-04): cinema, date, language and format filters; ONE showtime satisfies every showtime filter.

The rendered empty state and its 'Clear filters' control are asserted in frontend/src/features/browse/render.test.mjs.
The `rg 'Asia/Kolkata' backend/app/api backend/app/domain backend/app/models` clause is asserted as amended: every
hit is a line carrying P-ADM-25's published sentence (app/domain/admin/cinemas.py's ZONE_BAD).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import async_url
from app.domain.browse.catalogue import ListingFilters, listing_statement, load_zones
from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_lookup, make_movie, make_screen,
                           make_seat, make_showtime, owner_sql, reset_catalogue, settings_for)
from tests.xct._support import rg

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    cinema = make_cinema(db)
    hall4 = make_screen(db, cinema, "Hall 4")
    make_seat(db, hall4, "A", 1, 1, 1, make_category(db))
    f2d, f3d = make_lookup(db, "format", "2D"), make_lookup(db, "format", "3D")
    film = make_movie(db)
    make_showtime(db, film, hall4, "2026-08-17T11:00:00+05:30", format_id=f2d)
    make_showtime(db, film, hall4, "2026-08-18T11:00:00+05:30", format_id=f3d)
    return {"db": db, "cinema": cinema, "hall": hall4, "film": film, "2d": f2d, "3d": f3d}


def _clock() -> SetClock:
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    return clock


async def _count(c, **params) -> tuple[int, list]:
    r = await c.get("/api/movies", params=params)
    assert r.status_code == 200, r.text
    return r.json()["count"], r.json()["movies"]


async def test_one_showtime_must_satisfy_every_showtime_filter(world):
    async with api(world["db"], _clock()) as c:
        assert (await _count(c, date="2026-08-17"))[0] == 1
        assert (await _count(c, format_id=world["3d"]))[0] == 1
        assert await _count(c, date="2026-08-17", format_id=world["3d"]) == (0, [])
        assert (await _count(c))[0] == 1  # no date predicate, and no default to today
        assert (await _count(c, cinema_id=world["cinema"]))[0] == 1


def test_a_date_compiles_to_the_local_day_as_utc_instants():
    stmt = listing_statement(datetime(2026, 8, 15, tzinfo=timezone.utc), ListingFilters(date=date(2026, 8, 14)), {1: "Asia/Kolkata"})
    compiled = stmt.compile()
    text = str(compiled)
    assert "showtime.starts_at >=" in text and "showtime.starts_at <" in text
    instants = {v for v in compiled.params.values() if isinstance(v, datetime)}
    assert datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc) in instants
    assert datetime(2026, 8, 14, 18, 30, tzinfo=timezone.utc) in instants


async def test_the_local_day_boundary_includes_23_45_and_excludes_00_10(world):
    db = world["db"]
    late, early = make_movie(db), make_movie(db)
    make_showtime(db, late, world["hall"], "2026-08-14T23:45:00+05:30", "2026-08-15T01:45:00+05:30")
    make_showtime(db, early, world["hall"], "2026-08-15T00:10:00+05:30")
    async with api(db, _clock()) as c:
        _, movies = await _count(c, date="2026-08-14")
    ids = [m["id"] for m in movies]
    assert late in ids and early not in ids


async def test_the_zone_is_read_from_the_cinema_row(world):
    db = world["db"]
    owner_sql(db, "UPDATE cinema SET timezone = 'Asia/Dubai' WHERE id = %s", (world["cinema"],))
    engine = create_async_engine(async_url(settings_for(db).DATABASE_URL))
    try:
        async with engine.connect() as conn:
            zones = await load_zones(conn)
    finally:
        await engine.dispose()
    assert zones == {world["cinema"]: "Asia/Dubai"}
    params = listing_statement(datetime(2026, 8, 15, tzinfo=timezone.utc), ListingFilters(date=date(2026, 8, 14)), zones).compile().params
    instants = {v for v in params.values() if isinstance(v, datetime)}
    assert datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc) in instants
    assert datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc) in instants
    # and the request itself follows: 23:45 Dubai on the 14th is the 14th there
    film = make_movie(db)
    make_showtime(db, film, world["hall"], "2026-08-14T23:45:00+04:00", "2026-08-15T01:00:00+04:00")
    async with api(db, _clock()) as c:
        _, movies = await _count(c, date="2026-08-14")
    assert film in [m["id"] for m in movies]


P_ADM_25 = "That is not a time zone this system recognises. Enter an IANA zone name, such as Asia/Kolkata."


def test_the_zone_literal_appears_only_on_p_adm_25s_sentence():
    hits = rg("Asia/Kolkata", "backend/app/api", "backend/app/domain", "backend/app/models", fixed=True)
    assert [h for h in hits if P_ADM_25 not in h[2]] == []


@pytest.mark.parametrize("params,message", [
    ({"date": "14-08-2026"}, "That date is not valid."),
    ({"date": "2026-08-14T00:00:00"}, "That date is not valid."),
    ({"language_id": "0"}, "That filter is not valid."),
    ({"format_id": "abc"}, "That filter is not valid."),
    ({"cinema_id": "-3"}, "That filter is not valid."),
])
async def test_malformed_filters_are_422_with_their_own_sentence(world, params, message):
    async with api(world["db"], _clock()) as c:
        c.statements.reset()
        r = await c.get("/api/movies", params=params)
        assert c.statements.statements == []
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED" and r.json()["error"]["message"] == message


async def test_a_well_formed_id_matching_nothing_is_an_empty_200_and_page_is_ignored(world):
    async with api(world["db"], _clock()) as c:
        assert await _count(c, language_id="999999") == (0, [])
        plain = await c.get("/api/movies")
        paged = await c.get("/api/movies", params={"page": "2"})
    assert paged.content == plain.content

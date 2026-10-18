"""S-BRW-05 (P-BRW-04, EP-BRW-07): the filter vocabularies are the rows IN USE by what a caller can see now.

Not here (browser harness): which filter controls render and the 'Filters are unavailable right now.' line.
The server half of the outage case - /api/reference answering 503 DEPENDENCY_UNAVAILABLE when PostgreSQL is
unreachable - is asserted; the client's counting rule is unit-tested in frontend/src/features/browse.
"""

from __future__ import annotations

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_lookup, make_movie, make_screen,
                           make_seat, make_showtime, reset_catalogue)

pytestmark = pytest.mark.anyio


def _clock() -> SetClock:
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    return clock


@pytest.fixture
def db(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    return migrated_db


def seeded_catalogue(db) -> dict:
    cinema = make_cinema(db)
    hall = make_screen(db, cinema)
    make_seat(db, hall, "A", 1, 1, 1, make_category(db))
    langs = [make_lookup(db, "language") for _ in range(3)]
    certs = [make_lookup(db, "certification") for _ in range(2)]
    formats = [make_lookup(db, "format") for _ in range(2)]
    films = []
    for i in range(8):
        film = make_movie(db, language_id=langs[i % 3], certification_id=certs[i % 2])
        make_showtime(db, film, hall, f"2026-08-{16 + i % 4}T{10 + i}:00:00+05:30", format_id=formats[i % 2])
        films.append(film)
    return {"cinema": cinema, "hall": hall, "langs": langs, "certs": certs, "formats": formats, "films": films}


async def test_the_seeded_shape_returns_three_two_one_two_and_no_genres(db):
    seeded_catalogue(db)
    async with api(db, _clock()) as c:
        r = await c.get("/api/reference")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"cinemas", "languages", "formats", "certifications"}
    assert (len(body["languages"]), len(body["formats"]), len(body["cinemas"]), len(body["certifications"])) == (3, 2, 1, 2)
    for kind in body.values():
        for row in kind:
            assert set(row) == {"id", "name"}


async def test_a_withdrawn_row_a_visible_film_carries_is_returned_and_filters(db):
    world = seeded_catalogue(db)
    withdrawn = make_lookup(db, "language", active=False)
    film = make_movie(db, language_id=withdrawn)
    async with api(db, _clock()) as c:
        languages = (await c.get("/api/reference")).json()["languages"]
        filtered = (await c.get("/api/movies", params={"language_id": withdrawn})).json()["movies"]
    assert withdrawn in [row["id"] for row in languages]
    assert [m["id"] for m in filtered] == [film]
    assert world  # the rest of the catalogue is unchanged


async def test_rows_nothing_visible_uses_are_omitted(db):
    seeded_catalogue(db)
    unused = make_lookup(db, "language")
    draft_only = make_lookup(db, "language")
    make_movie(db, language_id=draft_only, published_at=None)
    lapsed_only = make_lookup(db, "language")
    make_movie(db, language_id=lapsed_only, display_until="2026-08-15T00:00:00+05:30")
    async with api(db, _clock()) as c:
        ids = [row["id"] for row in (await c.get("/api/reference")).json()["languages"]]
    assert unused not in ids and draft_only not in ids and lapsed_only not in ids


async def test_a_format_whose_only_showtime_is_past_its_cut_off_is_absent(db):
    world = seeded_catalogue(db)
    late = make_lookup(db, "format")
    # 11:30 + 15 minutes = 11:45, before the 12:00 clock: closed.
    make_showtime(db, world["films"][0], world["hall"], "2026-08-15T11:30:00+05:30", "2026-08-15T11:50:00+05:30", format_id=late)
    open_fmt = make_lookup(db, "format")
    # 11:50 + 15 = 12:05, after 12:00: still open, so present.
    make_showtime(db, world["films"][1], world["hall"], "2026-08-15T11:50:00+05:30", "2026-08-15T11:55:00+05:30", format_id=open_fmt)
    async with api(db, _clock()) as c:
        ids = [row["id"] for row in (await c.get("/api/reference")).json()["formats"]]
    assert late not in ids and open_fmt in ids


async def test_day_one_returns_empty_vocabularies(db):
    make_cinema(db)
    async with api(db, _clock()) as c:
        body = (await c.get("/api/reference")).json()
    assert body == {"cinemas": [], "languages": [], "formats": [], "certifications": []}


async def test_postgres_unreachable_is_503_dependency_unavailable(db):
    async with api(db, _clock(), DATABASE_URL="postgresql://frontrow_app:x@postgres:1/none") as c:
        r = await c.get("/api/reference")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert r.json()["error"]["message"] == "The site is temporarily unavailable. Please try again in a moment."

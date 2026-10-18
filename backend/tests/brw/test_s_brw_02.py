"""S-BRW-02 (P-BRW-02): the listing carries exactly the six details plus id, poster path and display_until.

Not here (browser harness): the card's rendered text, the img element's absence, the computed
-webkit-line-clamp values. The listing side of 'a missing poster still appears' is asserted.
"""

from __future__ import annotations

import pytest

from tests.brw.kit import SetClock, api, flush_redis, make_cinema, make_lookup, make_movie, owner_sql, reset_catalogue

pytestmark = pytest.mark.anyio

KEYS = {"id", "title", "synopsis", "runtime_minutes", "certification", "language", "genres", "poster_url", "display_until"}


@pytest.fixture
def db(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    make_cinema(migrated_db)  # the zone every instant is read in comes from the cinema row (P-BRW-01 precondition)
    return migrated_db


async def _listing(db) -> tuple[str, dict]:
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(db, clock) as c:
        r = await c.get("/api/movies")
    assert r.status_code == 200
    return r.text, r.json()


async def test_each_element_has_exactly_the_published_keys_and_lookups_are_id_and_name(db):
    with_genres = make_movie(db)
    g1, g2 = make_lookup(db, "genre", "DEMO GENRE B"), make_lookup(db, "genre", "DEMO GENRE A")
    owner_sql(db, "INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s), (%s, %s)", (with_genres, g1, with_genres, g2))
    bare = make_movie(db, poster_key=None)
    keyed = make_movie(db, poster_key="posters/absent-from-the-bucket.png")
    text, body = await _listing(db)
    assert body["count"] == 3 and len(body["movies"]) == 3
    by_id = {m["id"]: m for m in body["movies"]}
    for m in body["movies"]:
        assert set(m) == KEYS
        assert set(m["certification"]) == {"id", "name"} and set(m["language"]) == {"id", "name"}
        assert m["poster_url"] == f"/api/movies/{m['id']}/poster"
        assert isinstance(m["display_until"], str) and m["display_until"].endswith("+05:30")
    assert "code" not in text
    assert by_id[bare]["genres"] == []
    assert by_id[with_genres]["genres"] == [{"id": g2, "name": "DEMO GENRE A"}, {"id": g1, "name": "DEMO GENRE B"}]
    assert keyed in by_id  # a key whose object is missing from S3 does not remove the film from the listing


async def test_a_900_character_synopsis_is_returned_in_full(db):
    synopsis = ("x" * 899) + "y"
    film = make_movie(db, synopsis=synopsis)
    _, body = await _listing(db)
    assert [m["synopsis"] for m in body["movies"] if m["id"] == film] == [synopsis]

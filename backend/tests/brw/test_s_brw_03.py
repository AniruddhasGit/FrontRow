"""S-BRW-03 (P-BRW-03): newest first by published_at DESC, id DESC; one sort value; filters never reorder.

Not here (browser harness): the rendered listing has no select, listbox, combobox or 'Sort' control.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.browse.catalogue import ListingFilters, SortOption, listing_statement
from tests.brw.kit import SetClock, api, flush_redis, make_lookup, make_movie, reset_catalogue

pytestmark = pytest.mark.anyio


@pytest.fixture
def films(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    lang_ac, lang_b = make_lookup(db, "language"), make_lookup(db, "language")
    make_movie(db, movie_id=7, published_at="2026-08-12T10:00:00+05:30", language_id=lang_ac)
    make_movie(db, movie_id=11, published_at="2026-08-14T09:00:00+05:30", language_id=lang_b)
    make_movie(db, movie_id=12, published_at="2026-08-14T09:00:00+05:30", language_id=lang_ac)
    make_movie(db, movie_id=13, published_at=None, language_id=lang_ac)
    return db, lang_ac


def _clock() -> SetClock:
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    return clock


async def test_newest_first_with_id_descending_on_a_tie_ten_times_over(films):
    db, _ = films
    async with api(db, _clock()) as c:
        orders = [[m["id"] for m in (await c.get("/api/movies")).json()["movies"]] for _ in range(10)]
    assert orders == [[12, 11, 7]] * 10


async def test_sort_newest_is_the_default_byte_for_byte_and_nothing_else_is_accepted(films):
    db, _ = films
    async with api(db, _clock()) as c:
        default = await c.get("/api/movies")
        newest = await c.get("/api/movies", params={"sort": "newest"})
        refused = [await c.get("/api/movies", params={"sort": s}) for s in ("title", "price")]
    assert newest.content == default.content
    for r in refused:
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VALIDATION_FAILED"
        assert r.json()["error"]["message"] == "That sort option is not available."


def test_the_sort_enum_has_one_member_and_never_reaches_sql():
    assert len(list(SortOption)) == 1 and [m.value for m in SortOption] == ["newest"]
    text = str(listing_statement(datetime.fromisoformat("2026-08-15T12:00:00+05:30"), ListingFilters(), {}).compile())
    assert "newest" not in text


async def test_a_filter_narrows_and_does_not_reorder(films):
    db, lang_ac = films
    async with api(db, _clock()) as c:
        r = await c.get("/api/movies", params={"language_id": lang_ac})
    assert [m["id"] for m in r.json()["movies"]] == [12, 7]

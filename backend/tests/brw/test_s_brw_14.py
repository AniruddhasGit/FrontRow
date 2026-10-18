"""S-BRW-14 (P-BRW-16): the server orders categories by first appearance and guards one label per grid row.

The band derivation itself runs on the client and is unit-tested in frontend/src/features/seatmap
(bands.test.mjs) against this criterion's 6-row hall. Not here (browser harness): data-band / data-band-rule
element counts, the legend's rendered order and the mixed-rows notice.
"""

from __future__ import annotations

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_hall, make_movie, make_screen, make_seat,
                           make_showtime, reset_catalogue)

pytestmark = pytest.mark.anyio


@pytest.fixture
def db(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    return migrated_db


async def _map(db, st):
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(db, clock) as c:
        return await c.get(f"/api/showtimes/{st}/seatmap")


async def test_categories_are_ordered_by_first_grid_row_then_id_and_an_unused_one_is_absent(db):
    cinema = make_cinema(db)
    # created in this order so the LATER-created category appears FIRST on the map: id order is not the answer
    second, first = make_category(db, 1250), make_category(db, 0)
    make_category(db, 3333)  # assigned to no seat of this showtime
    mixed = [first] * 4 + [second] * 4
    hall = make_hall(db, cinema, rows=6, cols=8, categories=[[first] * 8, [first] * 8, None, [first] * 8, mixed, [second] * 8],
                     void_rows=(3,))
    body = (await _map(db, make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30"))).json()
    assert [c["id"] for c in body["categories"]] == [first, second]


async def test_two_categories_first_seen_on_one_grid_row_tie_break_on_id(db):
    cinema = make_cinema(db)
    a, b = make_category(db, 0), make_category(db, 1250)
    hall = make_hall(db, cinema, rows=2, cols=4, categories=[[b, b, a, a], [a] * 4])
    body = (await _map(db, make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30"))).json()
    assert [c["id"] for c in body["categories"]] == sorted([a, b])


async def test_two_labels_on_one_grid_row_is_a_500_with_no_seatmap_body(db):
    hall = make_screen(db, make_cinema(db))
    cat = make_category(db)
    make_seat(db, hall, "C", 1, 3, 1, cat)
    make_seat(db, hall, "D", 2, 3, 2, cat)
    r = await _map(db, make_showtime(db, make_movie(db), hall, "2026-08-16T19:30:00+05:30"))
    assert r.status_code == 500
    assert set(r.json()) == {"error"} and r.json()["error"]["code"] == "INTERNAL_ERROR" and r.json()["error"]["request_id"]

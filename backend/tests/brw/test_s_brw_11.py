"""S-BRW-11 (P-BRW-08): the seat map is the real layout of the hall, scoped to this showtime's frozen seat set.

The hall: 12 grid rows x 22 grid columns, columns 4 and 5 an aisle and grid row 6 a cross-aisle, so 11 seated
rows of 20 = 220 seats, and C-12 sits at gr 3, gc 14 (three seats, two aisle columns, then nine more).

Not here (browser harness): the 220 rendered cells, their accessible names, Enter/Space doing nothing, and the
rendered banners. The banner choice and the accessible names are unit-tested in frontend/src/features/seatmap.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.browse.seatmap import Seat
from tests.brw.kit import (SetClock, api, book_seat, flush_redis, make_category, make_cinema, make_hall, make_movie,
                           make_seat, make_showtime, owner_sql, reset_catalogue)

pytestmark = pytest.mark.anyio

SHOWTIME_KEYS = {"id", "starts_at", "sales_close_at", "sales_closed"}


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    cinema = make_cinema(db)
    cat = make_category(db, 1250, "Premium")
    hall = make_hall(db, cinema, rows=12, cols=22, categories=[cat] * 12, aisle_cols=(4, 5), void_rows=(6,))
    film = make_movie(db)
    st = make_showtime(db, film, hall["screen_id"], "2026-08-16T19:30:00+05:30")
    return {"db": db, "cinema": cinema, "cat": cat, "hall": hall, "film": film, "st": st}


async def _map(world, showtime_id=None):
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(world["db"], clock) as c:
        r = await c.get(f"/api/showtimes/{showtime_id or world['st']}/seatmap")
    return r


async def test_the_extent_order_and_coordinates_are_the_halls(world):
    r = await _map(world)
    assert r.status_code == 200
    body = r.json()
    assert (body["screen"]["rows"], body["screen"]["cols"]) == (12, 22)
    seats = body["seats"]
    assert len(seats) == 220
    assert [(s["gr"], s["gc"]) for s in seats] == sorted((s["gr"], s["gc"]) for s in seats)
    labels = [f"{s['row']}-{s['num']}" for s in seats]
    assert labels.index("A-2") < labels.index("A-12")
    c12 = next(s for s in seats if s["row"] == "C" and s["num"] == 12)
    assert (c12["row"], c12["num"], c12["gr"], c12["gc"]) == ("C", 12, 3, 14)
    taken = {(s["gr"], s["gc"]) for s in seats}
    assert not any(gc in (4, 5) for _, gc in taken) and not any(gr == 6 for gr, _ in taken)
    assert "blocked" not in r.text
    assert set(body["showtime"]) == SHOWTIME_KEYS
    assert all(type(s["is_active"]) is bool for s in seats)
    assert r.headers["cache-control"] == "no-store"


def test_a_seat_without_is_active_is_refused_at_model_construction():
    with pytest.raises(ValidationError):
        Seat(id=1, row="C", num=12, gr=3, gc=14, cat=1, price_paise=28124, state="available")


async def test_a_seat_added_later_is_not_in_this_showtimes_map(world):
    db = world["db"]
    make_seat(db, world["hall"]["screen_id"], "A", 21, 1, 23, world["cat"])
    body = (await _map(world)).json()
    assert body["screen"]["cols"] == 22 and len(body["seats"]) == 220
    assert not any(s["gc"] == 23 for s in body["seats"])


async def test_a_retired_seat_is_returned_inactive_with_its_true_state(world):
    db = world["db"]
    seat = world["hall"]["seats"]["C-12"]
    book_seat(db, world["st"], seat)
    owner_sql(db, "UPDATE seat SET is_active = false WHERE id = %s", (seat,))
    c12 = next(s for s in (await _map(world)).json()["seats"] if s["id"] == seat)
    assert (c12["is_active"], c12["state"]) == (False, "sold")


async def test_every_seat_retired_is_a_complete_200(world):
    owner_sql(world["db"], "UPDATE seat SET is_active = false WHERE screen_id = %s", (world["hall"]["screen_id"],))
    r = await _map(world)
    assert r.status_code == 200
    assert len(r.json()["seats"]) == 220 and all(s["is_active"] is False for s in r.json()["seats"])


async def test_an_empty_seat_set_is_a_500_with_the_request_id_of_its_log_line(world, log_capture):
    empty = make_showtime(world["db"], world["film"], world["hall"]["screen_id"], "2026-08-17T19:30:00+05:30", seat_set=False)
    r = await _map(world, empty)
    assert r.status_code == 500
    error = r.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["request_id"] in error["message"]
    lines = [ln for ln in log_capture.lines() if ln.get("request_id") == error["request_id"]]
    assert lines and any(ln.get("status_code") == 500 for ln in lines)


async def test_an_unknown_showtime_is_404_and_a_non_integer_is_422_before_any_statement(world):
    clock = SetClock()
    async with api(world["db"], clock) as c:
        missing = await c.get("/api/showtimes/999999/seatmap")
        c.statements.reset()
        bad = await c.get("/api/showtimes/abc/seatmap")
        assert c.statements.statements == []
    assert missing.status_code == 404 and missing.json()["error"]["message"] == "That showtime could not be found."
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALIDATION_FAILED"

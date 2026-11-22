"""CR-006: the demo schedule tops itself up on the listing read (app/domain/schedule.py), with no timer.

Two films, one hall, one showtime a day for a week. A listing read 3 days before the schedule ends, with a 21-day
horizon, copies the week forward (twice) with the films swapped, keeps each show's slot, price and changeover,
writes every copy's seat set, pushes the films' display windows, and a second read the same hour adds nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.brw.kit import (SetClock, api, book_seat, flush_redis, make_category, make_cinema, make_movie, make_screen, make_seat,
                           make_showtime, one, reset_catalogue)

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_screen(db, make_cinema(db))
    cat = make_category(db)
    for n in (1, 2):
        make_seat(db, hall, "A", n, 1, n, cat)
    a = make_movie(db, runtime=100, display_until="2026-08-22T00:00:00+05:30")
    b = make_movie(db, runtime=130, display_until="2026-08-22T00:00:00+05:30")
    for d in range(7):  # 15..21 Aug, 18:00, film a; 15 minutes of changeover after the film
        start = datetime.fromisoformat("2026-08-15T18:00:00+05:30") + timedelta(days=d)
        make_showtime(db, a, hall, start.isoformat(), (start + timedelta(minutes=115)).isoformat(), price=1299)
    return {"db": db, "a": a, "b": b, "hall": hall}


async def test_the_listing_read_copies_the_last_week_forward_rotated_and_only_once(world):
    db = world["db"]
    clock = SetClock()
    clock.set("2026-08-18T12:00:00+05:30")
    async with api(db, clock, DEMO_SHOWTIMES_AHEAD_DAYS="21") as c:
        assert (await c.get("/api/movies")).status_code == 200
        total = one(db, "SELECT count(*) FROM showtime")
        assert total == 21  # the week, copied twice: the schedule now reaches 4 Sep, past 18 Aug + 21 - 7
        # the first copy of 15 Aug: film b, same slot and price, b's runtime plus the same 15-minute changeover
        st = one(db, "SELECT movie_id || ',' || base_price_paise || ',' || extract(epoch FROM ends_at - starts_at)::int "
                     "FROM showtime WHERE starts_at = '2026-08-22T18:00:00+05:30'")
        assert st == f"{world['b']},1299,{(130 + 15) * 60}"
        # the second copy rotates back to film a
        assert one(db, "SELECT movie_id FROM showtime WHERE starts_at = '2026-08-29T18:00:00+05:30'") == world["a"]
        assert one(db, "SELECT count(*) FROM showtime_seat") == 21 * 2  # every copy has its seat set
        assert one(db, "SELECT count(*) FROM showtime WHERE seat_count_at_creation <> 2") == 0
        # each film stays visible through the day after its last new showtime
        assert one(db, "SELECT display_until > '2026-09-04T18:00:00+05:30' FROM movie WHERE id = %s", (world["a"],))
        assert (await c.get("/api/movies")).status_code == 200  # the same hour: the Redis key stops a second check
    assert one(db, "SELECT count(*) FROM showtime") == 21


async def test_off_by_default(world):
    clock = SetClock()
    clock.set("2026-08-18T12:00:00+05:30")
    async with api(world["db"], clock) as c:
        assert (await c.get("/api/movies")).status_code == 200
    assert one(world["db"], "SELECT count(*) FROM showtime") == 7


async def test_a_lapsed_schedule_restarts_in_the_current_week_not_the_past(world):
    """The schedule ended 21 Aug; nobody visited until 10 Sep. The copies jump to the current week."""
    db = world["db"]
    clock = SetClock()
    clock.set("2026-09-10T12:00:00+05:30")
    async with api(db, clock, DEMO_SHOWTIMES_AHEAD_DAYS="14") as c:
        assert (await c.get("/api/movies")).status_code == 200
        # nothing was written into the gap between the old schedule and now
        assert one(db, "SELECT count(*) FROM showtime WHERE starts_at > '2026-08-22T00:00:00+05:30' "
                       "AND starts_at < '2026-09-05T00:00:00+05:30'") == 0
        # today has a show, and the listing shows films again
        assert one(db, "SELECT count(*) FROM showtime WHERE starts_at::date = '2026-09-10'") == 1
        assert (await c.get("/api/movies")).json()["count"] >= 1


async def test_history_older_than_the_window_frees_the_seat_rows_and_keeps_every_booking(world):
    """CR-006 (owner ruling 2026-11-22): DEMO_HISTORY_DAYS deletes the seat rows of old showtimes and the old showtimes no
    booking references, through demo_delete_history (migration 0004). Bookings and payments are never touched, and the
    app role itself has no DELETE grant on those tables."""
    db = world["db"]
    seat_id = one(db, "SELECT min(id) FROM seat WHERE screen_id = %s", (world["hall"],))
    booked = one(db, "SELECT min(id) FROM showtime")  # 15 Aug, booked
    book_seat(db, booked, seat_id)
    clock = SetClock()
    clock.set("2026-10-01T12:00:00+05:30")  # with a 45-day window, 15 and 16 Aug are history
    from app.db import make_engine
    from app.domain import schedule
    from tests.brw.kit import settings_for
    engine = make_engine(settings_for(db))  # connects as frontrow_app: the restricted role can run the function
    async with engine.connect() as conn:
        assert await schedule.delete_history(conn, clock.now(), 45) == 1  # 16 Aug: nobody booked it
    await engine.dispose()
    assert one(db, "SELECT count(*) FROM showtime") == 6  # the booked 15 Aug show stays
    assert one(db, "SELECT count(*) FROM booking") == 1 and one(db, "SELECT count(*) FROM payment") == 1
    assert one(db, "SELECT count(*) FROM showtime_seat WHERE showtime_id = %s", (booked,)) == 0  # its seat rows went
    assert one(db, "SELECT count(*) FROM showtime_seat") == 5 * 2  # the five recent shows keep theirs
    assert one(db, "SELECT has_table_privilege('frontrow_app', 'showtime', 'DELETE')") is False


def test_the_function_refuses_a_cutoff_nearer_than_30_days(world):
    import psycopg
    with pytest.raises(psycopg.errors.RaiseException):
        one(world["db"], "SELECT demo_delete_history(now() - interval '29 days')")

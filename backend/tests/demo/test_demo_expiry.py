"""CR-012 (owner ruling 2026-11-23): "keep the old bookings for 6 months" - then the demo crowd's bookings of a show that
started more than 180 days ago are deleted with every row that references them (migration 0008 demo_delete_bookings,
schedule.delete_demo_bookings), and their shows go with the history. A real customer's booking never goes; neither
does anything sooner than six months, whatever DEMO_HISTORY_DAYS says. The clock is injected.
"""

from __future__ import annotations

from datetime import datetime

import psycopg
import pytest

from app.domain import schedule
from app.domain.booking import insert_demo_bookings
from app.domain.reference import new_reference
from tests.brw.kit import make_category, make_cinema, make_movie, make_screen, make_seat
from tests.pay.kit import api, book, clock_at, count, flush, owner_sql, r_call, reset, showtime, user

pytestmark = pytest.mark.anyio
NOW = "2026-08-15T09:30:00+00:00"  # six months before is 16 Feb 2026


@pytest.fixture(scope="module")
def world(migrated_db):
    db = migrated_db
    reset(db)
    flush()
    hall = make_screen(db, make_cinema(db), "Hall 1")
    cat = make_category(db, 0, "Standard")
    seats = [make_seat(db, hall, "A", n, 1, n, cat) for n in range(1, 13)]
    film = make_movie(db, title="The Long Night", display_from="2026-01-01T00:00:00+05:30", display_until="2026-12-31T00:00:00+05:30")
    shows = {name: showtime(db, film, hall, sid, starts) for name, sid, starts in (
        ("old", 1, "2026-01-10T20:00:00+05:30"),        # 217 days before: expires
        ("old_demo_only", 2, "2026-01-11T20:00:00+05:30"),  # expires, and then the show itself goes
        ("young", 3, "2026-03-01T20:00:00+05:30"),       # 167 days: kept
        ("unbooked_160", 4, "2026-03-08T20:00:00+05:30"),  # 160 days, nobody booked: kept despite DEMO_HISTORY_DAYS=150
    )}
    owner_sql(db, "SELECT setval(pg_get_serial_sequence('showtime', 'id'), (SELECT max(id) FROM showtime))")  # the top-up inserts
    crowd = [user(db, email=f"customer-{n}@demo.frontrow.invalid") for n in range(51, 56)]
    return {"db": db, "seats": seats, "shows": shows, "crowd": crowd}


def _seat_category(db, seat_id: int) -> int:
    return owner_sql(db, "SELECT seat_category_id FROM seat WHERE id = %s", (seat_id,))[0][0]


async def test_old_crowd_bookings_go_with_all_their_rows_in_bounded_batches_and_nothing_else_goes(world, monkeypatch):
    db, s, shows, crowd = world["db"], world["seats"], world["shows"], world["crowd"]
    cat = _seat_category(db, s[0])
    async with api(db, clock_at(NOW)) as c:
        async def demo(u, show, ids, at="2026-01-05T10:00:00+00:00"):
            async with c.application.state.db_engine.connect() as conn, conn.begin():
                await insert_demo_bookings(conn, [{"user_id": u, "showtime_id": show, "base_price_paise": 1299,
                                                   "at": datetime.fromisoformat(at), "seats": [(i, cat, 0) for i in ids]}],
                                           new_reference)
        for k in range(3):
            await demo(crowd[k], shows["old"], [s[2 * k], s[2 * k + 1]])  # 3 old demo bookings, 6 seats
        for k in range(2):
            await demo(crowd[k], shows["old_demo_only"], [s[k]])  # 2 more on a show only the crowd booked
        await demo(crowd[3], shows["young"], [s[0], s[1]], "2026-02-25T10:00:00+00:00")  # 167 days: kept
        real = user(db)
        book(db, real, shows["old"], [s[10]], created_at="2026-01-05T10:00:00Z")  # a real customer: never deleted
        book(db, crowd[4], shows["old"], [s[11]], created_at="2026-01-05T10:00:00Z")  # a crowd login used by hand: no mark
        total = {t: count(db, f"SELECT count(*) FROM {t}") for t in ("booking", "booking_seat", "payment", "receipt_dispatch")}
        assert total == {"booking": 8, "booking_seat": 12, "payment": 8, "receipt_dispatch": 6}

        monkeypatch.setattr(schedule, "BOOKING_BATCH", 3)
        async with c.application.state.db_engine.connect() as conn:
            assert await schedule.delete_demo_bookings(conn, c.clock.now()) == 3  # bounded: at most a batch per call
            assert await schedule.delete_demo_bookings(conn, c.clock.now()) == 2
            assert await schedule.delete_demo_bookings(conn, c.clock.now()) == 0  # idempotent: nothing left to do

    left = owner_sql(db, "SELECT b.user_id, b.showtime_id FROM booking b ORDER BY b.user_id, b.showtime_id")
    assert sorted(left) == sorted([(crowd[3], shows["young"]), (real, shows["old"]), (crowd[4], shows["old"])])
    # every row of a deleted booking went; nothing dangling, nothing else touched
    assert count(db, "SELECT count(*) FROM booking_seat") == 2 + 1 + 1
    assert count(db, "SELECT count(*) FROM receipt_dispatch") == 1
    assert count(db, "SELECT count(*) FROM payment") == 3
    assert count(db, "SELECT count(*) FROM payment p WHERE NOT EXISTS (SELECT 1 FROM booking b WHERE b.payment_id = p.id)") == 0
    assert count(db, "SELECT count(*) FROM users") == len(crowd) + 1  # accounts are never deleted


async def test_the_hourly_listing_check_expires_them_and_their_shows_but_never_sooner_than_six_months(world):
    db, s, shows, crowd = world["db"], world["seats"], world["shows"], world["crowd"]
    cat = _seat_category(db, s[0])
    async with api(db, clock_at(NOW)) as c:
        async with c.application.state.db_engine.connect() as conn, conn.begin():
            await insert_demo_bookings(conn, [{"user_id": crowd[0], "showtime_id": shows["old_demo_only"], "base_price_paise": 1299,
                                               "at": datetime.fromisoformat("2026-01-05T10:00:00+00:00"), "seats": [(s[5], cat, 0)]}],
                                       new_reference)
    r_call("DEL", "schedule:topup:checked")
    # the Render value: 150 days. The six-month floor wins, so the 160-day-old show stays.
    async with api(db, clock_at(NOW), DEMO_SHOWTIMES_AHEAD_DAYS="21", DEMO_HISTORY_DAYS="150") as c:
        assert (await c.get("/api/movies")).status_code == 200
    kept = {i for (i,) in owner_sql(db, "SELECT id FROM showtime")}
    assert shows["old_demo_only"] not in kept  # its crowd booking expired, then the show went with the history
    assert {shows["old"], shows["young"], shows["unbooked_160"]} <= kept  # a real booking holds "old"
    assert count(db, "SELECT count(*) FROM booking WHERE showtime_id = %s", (shows["old_demo_only"],)) == 0
    assert count(db, "SELECT count(*) FROM showtime_seat WHERE showtime_id = %s", (shows["unbooked_160"],)) > 0


def test_the_function_refuses_a_cutoff_inside_six_months_and_the_app_role_still_cannot_delete(world):
    db = world["db"]
    with psycopg.connect(db.app_url, autocommit=True) as conn, pytest.raises(psycopg.errors.RaiseException):
        conn.execute("SELECT demo_delete_bookings(now() - interval '179 days', 10)")
    for table in ("booking", "booking_seat", "payment", "receipt_dispatch"):
        assert owner_sql(db, f"SELECT has_table_privilege('frontrow_app', '{table}', 'DELETE')") == [(False,)]

"""Owner 2026-11-23: every demo show already has seats sold, filling toward 80-90% by its start
(app/domain/demo_fill.py). The fill writes real bookings, never takes a held or sold seat, is idempotent, runs at most
once an hour from the listing read, leaves every free seat bookable, and its sales show in the admin's figures.

A 112-seat hall (8 rows of 7 + aisle + 7, the back two rows premium) with 24 shows from 3 hours to 20 days ahead, and
60 crowd accounts. The clock is injected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import demo_fill
from app.domain.pricing import seat_price_paise
from tests.brw.kit import make_category, make_cinema, make_movie, make_screen, make_seat
from tests.pay.kit import (api, book, clock_at, confirm, cookies, count, flush, hold, owner_sql, r_call, reset, showtime,
                           user)

pytestmark = pytest.mark.anyio
NOW = "2026-08-15T09:30:00+00:00"
AHEAD = [0.125, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # days


@pytest.fixture(scope="module")
def world(migrated_db):
    db = migrated_db
    reset(db)
    flush()
    cinema = make_cinema(db)
    hall = make_screen(db, cinema, "Hall 1")
    standard, premium = make_category(db, 0, "Standard"), make_category(db, 1250, "Premium")
    seats = {}
    for r, row in enumerate("ABCDEFGH", 1):
        for n in range(1, 15):
            col = n if n <= 7 else n + 1  # an aisle after seat 7
            seats[(row, n)] = make_seat(db, hall, row, n, r, col, premium if row in "GH" else standard)
    film = make_movie(db, title="The Long Night", display_from="2026-08-01T00:00:00+05:30",
                      display_until="2026-12-31T00:00:00+05:30")
    now = datetime.fromisoformat(NOW)
    shows = [showtime(db, film, hall, 100 + i, (now + timedelta(days=d)).isoformat()) for i, d in enumerate(AHEAD)]
    crowd = [user(db, email=f"customer-{n}@demo.frontrow.invalid") for n in range(51, 111)]
    user(db, email="customer-07@demo.frontrow.invalid")  # a seed login: never a crowd account
    return {"db": db, "film": film, "hall": hall, "seats": seats, "shows": shows, "crowd": crowd}


def sold(db, show: int) -> int:
    return count(db, "SELECT count(*) FROM booking_seat WHERE showtime_id = %s", (show,))


async def run_fill(c, at: datetime, **kw) -> int:
    async with c.application.state.db_engine.connect() as conn:
        return await demo_fill.fill(conn, c.application.state.redis, at, horizon_days=21, **kw)


def test_the_target_rises_toward_the_show_and_ends_at_80_to_90_percent_on_average():
    z = timezone(timedelta(hours=5, minutes=30))
    starts = [datetime(2026, 8, 1, 11, tzinfo=z) + timedelta(days=i // 4, hours=(0, 3.5, 7, 10.5)[i % 4]) for i in range(4000)]
    finals = [demo_fill.final_share(i, s) for i, s in enumerate(starts)]
    assert 0.80 <= sum(finals) / len(finals) <= 0.90
    assert sum(f >= 0.96 for f in finals) > 100 and sum(f < 0.66 for f in finals) > 100  # some near sold out, some weak
    weekend_evening = [f for f, s in zip(finals, starts) if s.weekday() >= 4 and s.hour >= 17]
    weekday_morning = [f for f, s in zip(finals, starts) if s.weekday() < 4 and s.hour < 13]
    assert sum(weekend_evening) / len(weekend_evening) > sum(weekday_morning) / len(weekday_morning) + 0.08
    ramp = [demo_fill.ramp(d) for d in (21, 14, 7, 3, 1, 0.1, 0, -0.1)]
    assert ramp == sorted(ramp) and ramp[0] > 0.05 and ramp[-1] == 1.0  # always some seats sold, all by the start


async def test_the_fill_books_real_rows_in_side_by_side_groups_and_never_a_held_or_sold_seat(world):
    db, shows, seats = world["db"], world["shows"], world["seats"]
    near = shows[0]
    real = user(db)
    book(db, real, near, [seats[("E", 4)], seats[("E", 5)]])  # a customer's booking already there
    r_call("SET", f"lock:seat:{near}:{seats[('E', 6)]}", "someone-elses-hold", "PX", 600000)
    async with api(db, clock_at(NOW)) as c:
        written = await run_fill(c, datetime.fromisoformat(NOW))
    assert written > 0 and written == count(db, "SELECT count(*) FROM booking_seat bs JOIN booking b ON b.id = bs.booking_id "
                                                "WHERE b.user_id = ANY(%s)", (world["crowd"],))
    # the hold is untouched and was skipped; the fill left none of its own locks behind
    assert count(db, "SELECT count(*) FROM booking_seat WHERE seat_id = %s AND showtime_id = %s", (seats[("E", 6)], near)) == 0
    assert [k.decode() if isinstance(k, bytes) else k for k in r_call("KEYS", "lock:seat:*")] == [f"lock:seat:{near}:{seats[('E', 6)]}"]
    assert r_call("GET", f"lock:seat:{near}:{seats[('E', 6)]}") in (b"someone-elses-hold", "someone-elses-hold")
    # each show at its target for now; near shows nearly full, far ones lightly booked
    shares = []
    for show, d in zip(shows, AHEAD):
        starts = datetime.fromisoformat(NOW) + timedelta(days=d)
        want = round(112 * demo_fill.target_share(show, starts, datetime.fromisoformat(NOW), timezone(timedelta(hours=5, minutes=30))))
        assert sold(db, show) in (want, want - 1), (show, sold(db, show), want)  # a show 1 seat short waits for the next step
        shares.append(sold(db, show) / 112)
    assert shares[0] > 0.6 and max(shares[-5:]) < 0.3 and min(shares) > 0.05
    assert sum(shares[:3]) / 3 > sum(shares[-3:]) / 3 + 0.4
    # real bookings: captured payment with the seat total, priced from base + uplift, suppressed receipt, by the crowd
    rows = owner_sql(db, "SELECT b.id, b.user_id, b.total_paise, p.state, p.amount_paise, b.created_at, st.starts_at, "
                         "(SELECT status FROM receipt_dispatch r WHERE r.booking_id = b.id) FROM booking b "
                         "JOIN payment p ON p.id = b.payment_id JOIN showtime st ON st.id = b.showtime_id WHERE b.user_id <> %s",
                     (real,))
    assert rows and all(r[1] in world["crowd"] and r[3] == "captured" and r[2] == r[4] and r[7] == "suppressed" for r in rows)
    assert all(r[5] <= min(datetime.fromisoformat(NOW), r[6]) for r in rows)
    for booking_id, *_ in rows:
        lines = owner_sql(db, "SELECT s.grid_row, s.grid_col, bs.price_paise, st.base_price_paise, c.uplift_basis_points "
                              "FROM booking_seat bs JOIN seat s ON s.id = bs.seat_id JOIN seat_category c ON c.id = s.seat_category_id "
                              "JOIN showtime st ON st.id = bs.showtime_id WHERE bs.booking_id = %s ORDER BY s.grid_col", (booking_id,))
        assert 1 <= len(lines) <= 6 and len({r for r, *_ in lines}) == 1
        cols = [c for _, c, *_ in lines]
        assert cols == list(range(cols[0], cols[0] + len(cols))), cols  # side by side, never across the aisle
        assert all(price == seat_price_paise(base, up) for _, _, price, base, up in lines)
    sizes = [n for (n,) in owner_sql(db, "SELECT count(*) FROM booking_seat bs JOIN booking b ON b.id = bs.booking_id "
                                         "WHERE b.user_id <> %s GROUP BY b.id", (real,))]
    assert sizes.count(2) == max(sizes.count(k) for k in set(sizes))  # pairs are the commonest group
    # better seats go first: the centre of the premium rows fills before the front corners
    front_corners = [seats[(r, n)] for r in "AB" for n in (1, 14)]
    centre_back = [seats[(r, n)] for r in "FG" for n in (6, 7, 8, 9)]
    taken = lambda ids: count(db, "SELECT count(*) FROM booking_seat WHERE seat_id = ANY(%s)", (ids,)) / len(ids)  # noqa: E731
    assert taken(centre_back) > taken(front_corners)


async def test_it_is_idempotent_and_tops_up_as_time_passes(world):
    db = world["db"]
    before = count(db, "SELECT count(*) FROM booking_seat")
    async with api(db, clock_at(NOW)) as c:
        assert await run_fill(c, datetime.fromisoformat(NOW)) == 0
        assert count(db, "SELECT count(*) FROM booking_seat") == before
        later = datetime.fromisoformat(NOW) + timedelta(days=3)
        assert await run_fill(c, later) > 0
        assert await run_fill(c, later) == 0
    assert count(db, "SELECT count(*) FROM (SELECT showtime_id, seat_id FROM booking_seat GROUP BY 1, 2 HAVING count(*) > 1) x") == 0


async def test_the_listing_runs_it_at_most_once_an_hour_and_never_without_the_demo_setting(world):
    db = world["db"]
    clock = clock_at((datetime.fromisoformat(NOW) + timedelta(days=5)).isoformat())
    r_call("DEL", "schedule:topup:checked")
    async with api(db, clock) as c:  # the AWS setting: DEMO_SHOWTIMES_AHEAD_DAYS = 0
        before = count(db, "SELECT count(*) FROM booking_seat")
        assert (await c.get("/api/movies")).status_code == 200
        assert count(db, "SELECT count(*) FROM booking_seat") == before
    async with api(db, clock, DEMO_SHOWTIMES_AHEAD_DAYS="21") as c:
        assert (await c.get("/api/movies")).status_code == 200
        first = count(db, "SELECT count(*) FROM booking_seat")
        assert first > before
        clock.set((datetime.fromisoformat(NOW) + timedelta(days=6)).isoformat())
        assert (await c.get("/api/movies")).status_code == 200
        assert count(db, "SELECT count(*) FROM booking_seat") == first  # inside the hour: the Redis key says no
        r_call("DEL", "schedule:topup:checked")  # the hour is over
        assert (await c.get("/api/movies")).status_code == 200
        assert count(db, "SELECT count(*) FROM booking_seat") > first


async def test_a_customer_still_holds_and_books_a_free_seat_and_cannot_take_a_sold_one(world):
    db, show = world["db"], world["shows"][12]
    free = owner_sql(db, "SELECT ss.seat_id FROM showtime_seat ss WHERE ss.showtime_id = %s AND NOT EXISTS (SELECT 1 FROM booking_seat bs "
                         "WHERE bs.showtime_id = ss.showtime_id AND bs.seat_id = ss.seat_id) ORDER BY 1 LIMIT 1", (show,))[0][0]
    taken = owner_sql(db, "SELECT seat_id FROM booking_seat WHERE showtime_id = %s LIMIT 1", (show,))[0][0]
    customer = user(db)
    async with api(db, clock_at(NOW)) as c:
        r = await c.post(f"/api/showtimes/{show}/holds", json={"seat_ids": [taken]}, cookies=cookies(c, customer))
        assert r.status_code == 409, r.text
        r = await confirm(c, customer, (await hold(c, customer, [free], show))["hold_token"], key="1f2c1d4e-7b83-4a16-9c05-2e6f8a31b7d1",
                          showtime_id=show)
        assert r.status_code == 201, r.text
        seatmap = (await c.get(f"/api/showtimes/{show}/seatmap")).json()["seats"]
        assert {s["id"] for s in seatmap if s["state"] == "sold"} == {s for (s,) in owner_sql(
            db, "SELECT seat_id FROM booking_seat WHERE showtime_id = %s", (show,))}


async def test_the_admins_figures_count_the_demo_sales(world):
    db = world["db"]
    admin = user(db, role="admin")
    async with api(db, clock_at(NOW)) as c:
        body = (await c.get("/api/reports/dashboard", params={"period": "month", "date": "2026-08-15"},
                            cookies=cookies(c, admin, "admin"))).json()
    expected = owner_sql(db, "SELECT count(bs.id), sum(bs.price_paise) FROM booking_seat bs JOIN showtime st ON st.id = bs.showtime_id "
                             "WHERE st.starts_at >= '2026-07-31T18:30:00Z' AND st.starts_at < '2026-08-31T18:30:00Z'")[0]
    crowd_seats = count(db, "SELECT count(*) FROM booking_seat bs JOIN booking b ON b.id = bs.booking_id JOIN showtime st "
                            "ON st.id = bs.showtime_id WHERE b.user_id = ANY(%s) AND st.starts_at < '2026-08-31T18:30:00Z'",
                        (world["crowd"],))
    assert crowd_seats > 500 and (body["seats_sold"], body["takings_paise"]) == (expected[0], expected[1])

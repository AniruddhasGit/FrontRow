"""S-ADM-11 - edit a showtime, and list one hall's day (P-ADM-09).

Every clause is asserted here, including the Phase 4 one: a customer holding seats when the start moves 60 minutes
earlier still holds them, the hold token still resolving in Redis after the 200 (the seat lane's world, Redis 12).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.adm.kit import audit_rows, client, count, make_movie, make_screen, make_seats, make_showtime, routes, sign_in  # noqa: F401
from tests.dbkit import insert_booking, insert_user, owner_sql
from tests.xct._support import rg


def _one(db):
    hall = make_screen(db)
    make_seats(db, hall, 3)
    st = make_showtime(db, hall, make_movie(db), "2026-09-04T13:00:00Z", "2026-09-04T15:28:00Z")  # 18:30-20:58
    return hall, st


def _actions(db, st):
    return [r[0] for r in audit_rows(db, "entity_type = 'showtime' AND entity_id = %s", (st,))]


def test_one_row_per_kind_of_change(client):
    sign_in(client)
    _, st = _one(client.db)
    assert client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "base_price_paise": 30000}).status_code == 200
    assert _actions(client.db, st) == ["showtime.base_price_changed"]
    assert client.patch(f"/api/admin/showtimes/{st}", json={"version": 2, "starts_at": "2026-09-04 18:00"}).status_code == 200
    assert _actions(client.db, st)[1:] == ["showtime.updated"]
    r = client.patch(f"/api/admin/showtimes/{st}", json={"version": 3, "starts_at": "2026-09-04 17:30", "base_price_paise": 31000})
    assert r.status_code == 200 and r.json()["version"] == 4
    assert sorted(_actions(client.db, st)[2:]) == ["showtime.base_price_changed", "showtime.updated"]


def test_a_different_screen_id_is_422_and_writes_nothing(client):
    sign_in(client)
    _, st = _one(client.db)
    audits = count(client.db, "audit_log")
    r = client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "screen_id": make_screen(client.db)})
    assert (r.status_code, r.json()["error"]["message"]) == (422, "A showtime cannot be moved to a different hall. Create "
                                                                  "the showtime on the other hall instead.")
    assert count(client.db, "audit_log") == audits


def test_bounds_are_evaluated_on_the_merged_row_and_the_seat_set_never_moves(client):
    sign_in(client)
    _, st = _one(client.db)
    seat_set = (count(client.db, "showtime_seat", "showtime_id = %s", (st,)),
                owner_sql(client.db, "SELECT seat_count_at_creation FROM showtime WHERE id = %s", (st,)))
    for body in ({"starts_at": "2026-09-04 20:58"}, {"starts_at": "2026-09-04 21:30"}, {"ends_at": "2026-09-04 18:30"}):
        r = client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, **body})
        assert (r.status_code, r.json()["error"]["message"]) == (422, "The showtime must end after it starts."), body
    assert client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "ends_at": "2026-09-04 21:30"}).status_code == 200
    assert (count(client.db, "showtime_seat", "showtime_id = %s", (st,)),
            owner_sql(client.db, "SELECT seat_count_at_creation FROM showtime WHERE id = %s", (st,))) == seat_set


def test_the_overlap_check_runs_on_the_merged_interval_excluding_itself(client):
    sign_in(client)
    hall, st = _one(client.db)
    other = make_showtime(client.db, hall, make_movie(client.db), "2026-09-04T16:00:00Z", "2026-09-04T17:00:00Z")  # 21:30-22:30
    r = client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "ends_at": "2026-09-04 21:45"})
    assert r.status_code == 409 and [c["showtime_id"] for c in r.json()["error"]["details"]["conflicts"]] == [other]


def test_editing_a_booked_showtime_changes_nothing_about_its_bookings(client):
    sign_in(client)
    _, st = _one(client.db)
    seat_id, category = owner_sql(client.db, "SELECT s.id, s.seat_category_id FROM seat s JOIN showtime_seat ss ON "
                                             "ss.seat_id = s.id WHERE ss.showtime_id = %s LIMIT 1", (st,))[0]
    customer = insert_user(client.db, role="customer")
    booking = insert_booking(client.db, user_id=customer, reference="FRACDEFH",
                             showtime={"showtime_id": st, "seat_id": seat_id, "seat_category_id": category}, price_paise=25000)
    before = owner_sql(client.db, "SELECT price_paise FROM booking_seat WHERE booking_id = %s", (booking,))
    assert client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "base_price_paise": 40000,
                                                            "starts_at": "2026-09-04 17:30"}).status_code == 200
    assert owner_sql(client.db, "SELECT price_paise FROM booking_seat WHERE booking_id = %s", (booking,)) == before


def _day_fixture(db):
    hall = make_screen(db)
    make_seats(db, hall, 2)
    film = make_movie(db, runtime=60)
    ids = [make_showtime(db, hall, film, starts, ends) for starts, ends in (
        ("2026-09-04T04:30:00Z", "2026-09-04T05:30:00Z"), ("2026-09-04T08:30:00Z", "2026-09-04T09:30:00Z"),
        ("2026-09-04T13:05:00Z", "2026-09-04T14:05:00Z"), ("2026-09-04T16:00:00Z", "2026-09-04T17:00:00Z"))]
    return hall, ids


def test_the_day_list_and_include_past(client):
    sign_in(client)
    hall, (s601, s602, s603, s604) = _day_fixture(client.db)
    client.clock._now = datetime(2026, 9, 4, 13, 5, tzinfo=timezone.utc)  # the injected request instant
    q = {"screen_id": hall, "date": "2026-09-04"}
    every = [s601, s602, s603, s604]
    assert [i["id"] for i in client.get("/api/admin/showtimes", params=q).json()["items"]] == every
    assert [i["id"] for i in client.get("/api/admin/showtimes", params={**q, "include_past": "true"}).json()["items"]] == every
    assert [i["id"] for i in client.get("/api/admin/showtimes", params={**q, "include_past": "false"}).json()["items"]] == [s604]
    item = client.get("/api/admin/showtimes", params=q).json()["items"][0]
    assert set(item) == {"id", "movie_id", "movie_title", "starts_at", "ends_at", "base_price_paise",
                         "seat_count_at_creation", "booked_seat_count", "version"}
    assert item["starts_at"] == "2026-09-04T10:00:00"


def test_the_list_takes_exactly_three_query_parameters_and_validates_each(client):
    sign_in(client)
    hall, _ = _day_fixture(client.db)
    route = next(r for r in routes(client.app) if r.path == "/api/admin/showtimes" and "GET" in r.methods)
    assert sorted(p.name for p in route.dependant.query_params) == ["date", "include_past", "screen_id"]
    for params, message in (({"date": "2026-09-04"}, "That hall no longer exists. Choose a hall from the list."),
                            ({"screen_id": "abc", "date": "2026-09-04"}, "That hall no longer exists. Choose a hall from the list."),
                            ({"screen_id": hall, "date": "2026-13-45"}, "That date is not valid."),
                            ({"screen_id": hall, "date": "2026-09-04", "include_past": "maybe"}, "That filter value is not valid.")):
        r = client.get("/api/admin/showtimes", params=params)
        assert (r.status_code, r.json()["error"]["message"]) == (422, message), params
    r = client.get("/api/admin/showtimes", params={"screen_id": 987654321, "date": "2026-09-04"})
    assert (r.status_code, r.json()["error"]["message"]) == (404, "That hall no longer exists at this address.")


def test_now_is_read_only_through_the_injected_clock():
    hits = rg(r"datetime[.]now[(][)]|datetime[.]utcnow|time[.]time[(][)]", "backend/app")
    assert [h for h in hits if h[0] != "backend/app/core/clock.py"] == []


@pytest.mark.anyio
async def test_a_hold_survives_the_start_moving_60_minutes_earlier(migrated_db):
    from tests.sea.kit import T0, SetClock, api, r_call, r_keys, session, user, world77

    w = world77(migrated_db)
    owner_sql(migrated_db, "UPDATE showtime SET starts_at = starts_at + interval '2 days', ends_at = ends_at + interval '2 days' "
                           "WHERE id = 88")  # 88 shares 77's hall and hour; moved off so only the start move is tested
    clock = SetClock()
    clock.set(T0)
    customer, admin = user(w["db"]), user(w["db"], "admin")
    async with api(w["db"], clock) as c:
        mine = session(c, customer)
        hold = (await c.post("/api/showtimes/77/holds", json={"seat_ids": [401, 402]}, cookies=mine)).json()
        token = hold["hold_token"]
        locks = r_keys("lock:seat:77:*")
        r = await c.patch("/api/admin/showtimes/77", json={"version": 1, "starts_at": "2026-08-14 18:30"},
                          cookies=session(c, admin, "admin"))  # 19:30 -> 18:30 local
        assert r.status_code == 200, r.text
        assert r.json()["starts_at"] == "2026-08-14T18:30:00"
        assert r_call("EXISTS", f"hold:{token}") == 1
        assert r_keys("lock:seat:77:*") == locks == ["lock:seat:77:401", "lock:seat:77:402"]
        assert {r_call("GET", k) for k in locks} == {token}
        still = await c.get(f"/api/holds/{token}", cookies=mine)
        assert still.status_code == 200 and [s["seat_id"] for s in still.json()["seats"]] == [401, 402]

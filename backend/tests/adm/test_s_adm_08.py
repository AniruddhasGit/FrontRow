"""S-ADM-08 - a showtime's seat set is written at creation and never moves (P-ADM-14)."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError

from tests.adm.kit import client, count, make_category, make_movie, make_screen, make_seats, routes, sign_in  # noqa: F401
from tests.dbkit import owner_sql

NOT_FOUND = "That page does not exist."


def _create(client, hall, movie, day: int) -> int:
    r = client.post("/api/admin/showtimes", json={"movie_id": movie, "screen_id": hall,
                                                   "starts_at": f"2026-09-{day:02d} 10:00", "ends_at": f"2026-09-{day:02d} 12:00",
                                                   "base_price_paise": 25000})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _set(db, st) -> tuple[int, int]:
    return (count(db, "showtime_seat", "showtime_id = %s", (st,)),
            owner_sql(db, "SELECT seat_count_at_creation FROM showtime WHERE id = %s", (st,))[0][0])


def test_the_sequence_501_to_504(client):
    sign_in(client)
    db = client.db
    hall, movie = make_screen(db), make_movie(db, runtime=120)
    make_seats(db, hall, 90)
    s501 = _create(client, hall, movie, 1)
    assert _set(db, s501) == (90, 90)
    j11 = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [
        {"row_label": "J", "seat_number": 11, "grid_row": 10, "grid_col": 11,
         "seat_category_id": make_category(db)}]}).json()["items"][0]["id"]
    s502 = _create(client, hall, movie, 2)
    assert _set(db, s502) == (91, 91)
    assert client.patch(f"/api/admin/seats/{j11}", json={"is_active": False}).status_code == 200
    s503 = _create(client, hall, movie, 3)
    assert _set(db, s503) == (90, 90)
    recorded = _set(db, s503)
    assert client.patch(f"/api/admin/seats/{j11}", json={"is_active": True}).status_code == 200
    assert _set(db, s503) == recorded == (90, 90)  # restoring J11 does NOT add it to 503
    s504 = _create(client, hall, movie, 4)
    assert _set(db, s504) == (91, 91)
    assert _set(db, s501) == (90, 90)
    for st in (s501, s502, s503, s504):
        before = _set(db, st)
        assert client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, "base_price_paise": 30000}).status_code == 200
        assert _set(db, st) == before
    assert count(db, "showtime s", "s.seat_count_at_creation <> (SELECT count(*) FROM showtime_seat ss "
                                   "WHERE ss.showtime_id = s.id)") == 0


def test_zero_seats_in_service_is_409_and_no_showtime_is_written(client):
    sign_in(client)
    hall = make_screen(client.db)
    seats = make_seats(client.db, hall, 2)
    owner_sql(client.db, "UPDATE seat SET is_active = false WHERE id = ANY(%s)", (seats,))
    before = count(client.db, "showtime")
    r = client.post("/api/admin/showtimes", json={"movie_id": make_movie(client.db), "screen_id": hall,
                                                   "starts_at": "2026-09-05 10:00", "ends_at": "2026-09-05 12:00",
                                                   "base_price_paise": 25000})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "LAYOUT_FROZEN")
    assert count(client.db, "showtime") == before


def test_both_unique_indexes_exist_by_name_and_are_different_jobs(client):
    rows = set(owner_sql(client.db, "SELECT table_name, constraint_name, constraint_type FROM information_schema.table_constraints "
                                    "WHERE table_name IN ('showtime_seat','booking_seat') AND constraint_type IN ('UNIQUE','PRIMARY KEY')"))
    assert ("booking_seat", "uq_booking_seat__showtime_id_seat_id", "UNIQUE") in rows  # THE oversell guard
    # PostgreSQL folds a UNIQUE that duplicates the PRIMARY KEY of the same CREATE TABLE into it, keeping the
    # unique's name: the constraint exists by name, typed PRIMARY KEY. Not the guard either way.
    assert ("showtime_seat", "uq_showtime_seat__showtime_id_seat_id", "PRIMARY KEY") in rows


def test_no_route_edits_a_seat_set_and_such_addresses_are_404(client):
    sign_in(client)
    assert [r.path for r in routes(client.app) if "showtime_seat" in r.path or r.path.startswith("/api/admin/showtimes/{showtime_id}/seats")] == []
    for r in (client.post("/api/admin/showtimes/501/seats", json={}), client.delete("/api/admin/showtimes/501/seats/77")):
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (404, "NOT_FOUND", NOT_FOUND)


def test_a_failing_seat_set_insert_is_503_and_leaves_no_showtime(client, monkeypatch):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 3)
    movie = make_movie(client.db)

    async def boom(*args, **kwargs):
        raise OperationalError("INSERT INTO showtime_seat ...", {}, Exception("connection lost"))

    monkeypatch.setattr("app.domain.admin.showtimes.write_seat_set", boom)
    before = count(client.db, "showtime")
    r = client.post("/api/admin/showtimes", json={"movie_id": movie, "screen_id": hall, "starts_at": "2026-09-06 10:00",
                                                   "ends_at": "2026-09-06 12:00", "base_price_paise": 25000})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert r.json()["error"]["message"] == ("The system cannot reach its database right now. Nothing was saved. "
                                            "Try again in a moment.")
    assert count(client.db, "showtime") == before

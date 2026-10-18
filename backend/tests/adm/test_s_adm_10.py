"""S-ADM-10 - two showtimes may not overlap on one hall; intervals are half-open (P-ADM-08)."""

from __future__ import annotations

import threading

from sqlalchemy import event

from tests.adm.kit import client, count, make_cinema, make_movie, make_screen, make_seats, make_showtime, sign_in  # noqa: F401
from tests.xct._support import rg


def _screen3(db):
    hall = make_screen(db, make_cinema(db), name="Screen 3")
    make_seats(db, hall, 4)
    film = make_movie(db, title="DEMO MOVIE 04")
    st41 = make_showtime(db, hall, film, "2026-09-04T13:00:00Z", "2026-09-04T15:28:00Z")  # 18:30-20:58 local
    return hall, film, st41


def _create(client, hall, film, starts, ends):
    return client.post("/api/admin/showtimes", json={"movie_id": film, "screen_id": hall, "starts_at": f"2026-09-04 {starts}",
                                                      "ends_at": f"2026-09-04 {ends}", "base_price_paise": 25000})


def test_overlap_is_409_and_the_zero_gap_and_later_creates_are_201(client):
    sign_in(client)
    hall, film, st41 = _screen3(client.db)
    r = _create(client, hall, film, "20:45", "22:40")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "SHOWTIME_OVERLAP")
    assert r.json()["error"]["message"] == ("Screen 3 already has a showtime from 6:30 pm to 8:58 pm on 4 Sep 2026. Two "
                                            "showtimes cannot run in one hall at the same time. Choose a different time or "
                                            "a different hall.")
    conflicts = r.json()["error"]["details"]["conflicts"]
    assert conflicts == [{"showtime_id": st41, "movie_title": "DEMO MOVIE 04", "starts_at": "2026-09-04T18:30:00",
                          "ends_at": "2026-09-04T20:58:00"}]
    assert _create(client, hall, film, "20:58", "22:53").status_code == 201  # 20:58 > 20:58 is false


def test_c_at_21_15_is_201_and_two_conflicts_give_an_array_of_two(client):
    sign_in(client)
    hall, film, _ = _screen3(client.db)
    assert _create(client, hall, film, "21:15", "23:10").status_code == 201
    r = _create(client, hall, film, "19:00", "22:00")
    assert r.status_code == 409
    assert isinstance(r.json()["error"]["details"]["conflicts"], list) and len(r.json()["error"]["details"]["conflicts"]) == 2
    assert r.json()["error"]["message"] == ("Screen 3 already has 2 showtimes in that period. Two showtimes cannot run in "
                                            "one hall at the same time. Choose a different time or a different hall.")
    for entry in r.json()["error"]["details"]["conflicts"]:
        assert set(entry) == {"showtime_id", "movie_title", "starts_at", "ends_at"}


def test_the_edit_predicate_excludes_its_own_row_as_captured_from_the_statement(client):
    sign_in(client)
    hall, film, st41 = _screen3(client.db)
    seen: list[str] = []
    engine = client.app.state.db_engine.sync_engine

    def record(conn, cursor, statement, *args):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        r = client.patch(f"/api/admin/showtimes/{st41}", json={"version": 1, "starts_at": "2026-09-04 18:40",
                                                                "ends_at": "2026-09-04 21:08"})
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert r.status_code == 200, r.text  # moving into its own old interval is not an overlap
    overlap = [s for s in seen if "showtime.starts_at <" in s and "showtime.ends_at >" in s]
    assert len(overlap) == 1 and "showtime.id !=" in overlap[0]
    seen.clear()
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert _create(client, hall, film, "23:00", "23:30").status_code == 201
    finally:
        event.remove(engine, "before_cursor_execute", record)
    overlap = [s for s in seen if "showtime.starts_at <" in s and "showtime.ends_at >" in s]
    assert len(overlap) == 1 and "showtime.id !=" not in overlap[0]


def test_two_concurrent_overlapping_creates_produce_one_201_and_one_409(client):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 2)
    film = make_movie(client.db)
    before = count(client.db, "showtime", "screen_id = %s", (hall,))
    results: list[int] = []
    barrier = threading.Barrier(2)

    def fire(starts, ends):
        barrier.wait()
        results.append(_create(client, hall, film, starts, ends).status_code)

    threads = [threading.Thread(target=fire, args=a) for a in (("10:00", "12:00"), ("11:00", "13:00"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(results) == [201, 409]
    assert count(client.db, "showtime", "screen_id = %s", (hall,)) == before + 1


def test_no_changeover_minimum_exists_anywhere():
    assert rg(r"turnaround|changeover|MIN_GAP|MINIMUM_GAP|cleanup_minutes", "backend/app", "backend/migrations",
              "frontend/src", "scripts") == []

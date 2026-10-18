"""S-ADM-06 - lay out a hall's seats while it has no showtimes (P-ADM-13, EP-ADM-18..21)."""

from __future__ import annotations

import threading
import time

import psycopg

from tests.adm.kit import audit_rows, client, count, make_category, make_screen, make_seat, sign_in  # noqa: F401
from tests.dbkit import owner_sql

DUP_TAIL = "already exist in this hall. Every seat in a hall needs its own row and number."


def _seats(category: int, n: int, row: str = "A", start: int = 1, grid_row: int = 1) -> list[dict]:
    return [{"row_label": row, "seat_number": start + i, "grid_row": grid_row, "grid_col": start + i,
             "seat_category_id": category} for i in range(n)]


def _wide(category: int, n: int) -> list[dict]:
    return [{"row_label": "A" * (1 + i // 125), "seat_number": i % 125 + 1, "grid_row": i // 125 + 1,
             "grid_col": i % 125 + 1, "seat_category_id": category} for i in range(n)]


def test_a_batch_of_500_is_201_and_501_is_422(client):
    sign_in(client)
    category = make_category(client.db)
    assert client.post(f"/api/admin/screens/{make_screen(client.db)}/seats", json={"seats": _wide(category, 500)}).status_code == 201
    r = client.post(f"/api/admin/screens/{make_screen(client.db)}/seats", json={"seats": _wide(category, 501)})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")


def test_three_label_collisions_are_named_in_submitted_order_and_nothing_is_written(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    for n in (12, 13, 14):
        make_seat(client.db, hall, f"C{n}", category, grid=(3, n))
    before = count(client.db, "seat", "screen_id = %s", (hall,))
    batch = [{"row_label": "C", "seat_number": n, "grid_row": 9, "grid_col": n, "seat_category_id": category}
             for n in (11, 12, 13, 14, 15)]
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": batch})
    assert r.status_code == 422
    assert r.json()["error"]["details"] == {"duplicate_labels": ["C12", "C13", "C14"]}
    assert r.json()["error"]["message"] == f"Seats C12, C13 and C14 {DUP_TAIL}"
    assert count(client.db, "seat", "screen_id = %s", (hall,)) == before


def test_one_label_collision_is_the_singular_sentence(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    make_seat(client.db, hall, "C13", category, grid=(3, 13))
    batch = [{"row_label": "C", "seat_number": n, "grid_row": 9, "grid_col": n, "seat_category_id": category}
             for n in (11, 12, 13, 14, 15)]
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": batch})
    assert r.json()["error"]["details"] == {"duplicate_labels": ["C13"]}
    assert r.json()["error"]["message"] == "Seat C13 already exists in this hall. Every seat in a hall needs its own row and number."


def test_coordinate_collisions_name_a_count_never_a_label(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    two_at_one = [{"row_label": "D", "seat_number": 1, "grid_row": 4, "grid_col": 1, "seat_category_id": category},
                  {"row_label": "D", "seat_number": 2, "grid_row": 4, "grid_col": 1, "seat_category_id": category}]
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": two_at_one})
    assert r.status_code == 422 and "duplicate_coordinates" in r.json()["error"]["details"]
    assert r.json()["error"]["message"] == "Another seat is already drawn at that position in the map. Choose a different position."
    for n in (1, 2, 3):
        make_seat(client.db, hall, f"E{n}", category, grid=(5, n))
    three = [{"row_label": "F", "seat_number": n, "grid_row": 5, "grid_col": n, "seat_category_id": category} for n in (1, 2, 3)]
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": three})
    assert r.json()["error"]["message"] == ("Another seat is already drawn at 3 of those positions in the map. "
                                            "Choose different positions.")
    assert len(r.json()["error"]["details"]["duplicate_coordinates"]) == 3


def test_each_field_bound_is_refused_with_its_sentence(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    good = {"row_label": "G", "seat_number": 1, "grid_row": 7, "grid_col": 1, "seat_category_id": category}
    cases = [({"seat_category_id": 987654321}, "That seat category is not on the list. Choose one of the listed categories."),
             ({"seat_number": 0}, "Enter a seat number of 1 or more."),
             ({"grid_row": 0}, "Enter a row and column position of 1 or more."),
             ({"row_label": "ABCDE"}, "Enter a row label of 1 to 4 letters, for example A or AA."),
             ({"row_label": "A1"}, "Enter a row label of 1 to 4 letters, for example A or AA.")]
    for change, message in cases:
        r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [{**good, **change}]})
        assert (r.status_code, r.json()["error"]["message"]) == (422, message), change
    assert count(client.db, "seat", "screen_id = %s", (hall,)) == 0


def test_row_label_is_stored_upper_trimmed_ascii_only_and_i_is_allowed(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [
        {"row_label": " i ", "seat_number": 1, "grid_row": 1, "grid_col": 1, "seat_category_id": category}]})
    assert r.status_code == 201 and r.json()["items"][0]["row_label"] == "I"
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [
        {"row_label": "ß", "seat_number": 2, "grid_row": 1, "grid_col": 2, "seat_category_id": category}]})
    assert r.status_code == 422  # SRC-004 JC-R6-03: ASCII A-Z only


def test_before_any_showtime_a_seat_may_be_edited_and_deleted_each_with_its_audit_row(client):
    sign_in(client)
    hall, category, other = make_screen(client.db), make_category(client.db), make_category(client.db)
    seat = make_seat(client.db, hall, "C12", category, grid=(3, 12))
    for change in ({"row_label": "D"}, {"seat_number": 14}, {"seat_category_id": other}):
        r = client.patch(f"/api/admin/seats/{seat}", json=change)
        assert r.status_code == 200, (change, r.text)
    assert [a[0] for a in audit_rows(client.db, "entity_type = 'seat' AND entity_id = %s", (seat,))] == ["seat.updated"] * 3
    r = client.delete(f"/api/admin/seats/{seat}")
    assert r.status_code == 204
    assert count(client.db, "seat", "id = %s", (seat,)) == 0
    assert audit_rows(client.db, "entity_type = 'seat' AND entity_id = %s", (seat,))[-1][0] == "seat.deleted"


def test_the_seat_list_is_in_drawing_order_with_the_frozen_state(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    b = make_seat(client.db, hall, "B1", category, grid=(2, 1))
    a2 = make_seat(client.db, hall, "A2", category, grid=(1, 2))
    a1 = make_seat(client.db, hall, "A1", category, grid=(1, 1))
    body = client.get(f"/api/admin/screens/{hall}/seats").json()
    assert [s["id"] for s in body["items"]] == [a1, a2, b]
    assert (body["has_showtimes"], body["showtime_count"]) == (False, 0)


def test_a_seat_write_waits_on_the_screen_row_lock(client):
    """The second transaction holds FOR UPDATE on the screen row; the API's insert must wait on it."""
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    result = {}
    with psycopg.connect(client.db.owner_url) as holder:
        # FOR SHARE, not FOR UPDATE: it blocks only a writer that takes FOR UPDATE on the screen row, and lets
        # the FOR KEY SHARE that a foreign-key check takes pass - so a wait proves the explicit lock, not the FK.
        holder.execute("SELECT id FROM screen WHERE id = %s FOR SHARE", (hall,))

        def fire():
            result["r"] = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": _seats(category, 1)})

        thread = threading.Thread(target=fire)
        thread.start()
        waiting = []
        for _ in range(100):  # polling the DATABASE's lock table, not a clock: the lock is the database's
            waiting = owner_sql(client.db, "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                           "WHERE NOT l.granted AND a.usename = 'frontrow_app' AND a.datname = current_database()")
            if waiting:
                break
            time.sleep(0.05)
        assert len(waiting) == 1
        pid = waiting[0][0]
        assert owner_sql(client.db, "SELECT count(*) FROM pg_locks WHERE granted = false AND pid = %s", (pid,)) == [(1,)]
        assert thread.is_alive() and "r" not in result
        holder.rollback()  # release
    thread.join(timeout=10)
    assert result["r"].status_code == 201

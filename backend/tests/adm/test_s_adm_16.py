"""S-ADM-16 - take a seat out of service and return it (P-ADM-15).

Every clause is asserted here, including GET /api/me/bookings/{reference} (EP-ACC-08) still rendering the retired
seat's original row_label and seat_number. That endpoint rate-limits through Redis, so its test uses cached_client
(this lane's Redis database 9).
"""

from __future__ import annotations

import threading
import time

import psycopg

from tests.adm.kit import (audit_rows, cached_client, client, count, make_category, make_movie, make_screen, make_seat, make_seats,  # noqa: F401
                           make_showtime, routes, sign_in)
from app.domain.reference import new_reference
from tests.dbkit import insert_booking, insert_user, owner_sql


def _hall(db):
    hall, category = make_screen(db), make_category(db)
    seat = make_seat(db, hall, "C12", category, grid=(3, 12))
    make_seats(db, hall, 3, category)
    return hall, seat, category


def test_toggles_write_their_rows_and_a_repeat_is_409_with_its_sentence(client):
    sign_in(client)
    hall, seat, _ = _hall(client.db)
    assert client.patch(f"/api/admin/seats/{seat}", json={"is_active": False}).status_code == 200
    r = client.patch(f"/api/admin/seats/{seat}", json={"is_active": False})
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, "LAYOUT_FROZEN",
                                                                                         "Seat C12 is already out of service.")
    assert client.patch(f"/api/admin/seats/{seat}", json={"is_active": True}).status_code == 200
    r = client.patch(f"/api/admin/seats/{seat}", json={"is_active": True})
    assert r.json()["error"]["message"] == "Seat C12 is already in service."
    rows = audit_rows(client.db, "entity_type = 'seat' AND entity_id = %s", (seat,))
    assert [(a, b, c) for a, _, _, b, c, _ in rows] == [("seat.deactivated", {"is_active": True}, {"is_active": False}),
                                                        ("seat.reactivated", {"is_active": False}, {"is_active": True})]


def test_the_toggle_waits_on_the_screen_row_lock(client):
    sign_in(client)
    hall, seat, _ = _hall(client.db)
    result = {}
    with psycopg.connect(client.db.owner_url) as holder:
        # FOR SHARE, not FOR UPDATE: it blocks only a writer that takes FOR UPDATE on the screen row, and lets
        # the FOR KEY SHARE that a foreign-key check takes pass - so a wait proves the explicit lock, not the FK.
        holder.execute("SELECT id FROM screen WHERE id = %s FOR SHARE", (hall,))
        thread = threading.Thread(target=lambda: result.setdefault("r", client.patch(f"/api/admin/seats/{seat}",
                                                                                     json={"is_active": False})))
        thread.start()
        waiting = []
        for _ in range(100):
            waiting = owner_sql(client.db, "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE NOT "
                                           "l.granted AND a.usename = 'frontrow_app' AND a.datname = current_database()")
            if waiting:
                break
            time.sleep(0.05)
        assert owner_sql(client.db, "SELECT count(*) FROM pg_locks WHERE granted = false AND pid = %s", (waiting[0][0],)) == [(1,)]
        assert "r" not in result
        holder.rollback()
    thread.join(timeout=10)
    assert result["r"].status_code == 200


def test_existing_showtimes_keep_the_seat_and_later_ones_do_not_get_it_back(client):
    sign_in(client)
    hall, seat, category = _hall(client.db)
    movie = make_movie(client.db)
    existing = make_showtime(client.db, hall, movie, "2026-09-01T10:00:00Z", "2026-09-01T12:00:00Z")
    customer = insert_user(client.db, role="customer")
    insert_booking(client.db, user_id=customer, reference="FRCDEFHJ",
                   showtime={"showtime_id": existing, "seat_id": seat, "seat_category_id": category}, price_paise=25000)
    snapshot = lambda st: (count(client.db, "showtime_seat", "showtime_id = %s", (st,)),  # noqa: E731
                           owner_sql(client.db, "SELECT seat_count_at_creation FROM showtime WHERE id = %s", (st,)))
    before, sold = snapshot(existing), count(client.db, "booking_seat", "seat_id = %s", (seat,))
    assert client.patch(f"/api/admin/seats/{seat}", json={"is_active": False}).status_code == 200
    assert snapshot(existing) == before
    assert count(client.db, "booking_seat", "seat_id = %s", (seat,)) == sold == 1
    created_while_out = client.post("/api/admin/showtimes", json={"movie_id": movie, "screen_id": hall,
                                                                  "starts_at": "2026-09-02 10:00", "ends_at": "2026-09-02 12:00",
                                                                  "base_price_paise": 25000}).json()["id"]
    assert count(client.db, "showtime_seat", "showtime_id = %s AND seat_id = %s", (created_while_out, seat)) == 0
    out_count = count(client.db, "showtime_seat", "showtime_id = %s", (created_while_out,))
    assert client.patch(f"/api/admin/seats/{seat}", json={"is_active": True}).status_code == 200
    assert count(client.db, "showtime_seat", "showtime_id = %s", (created_while_out,)) == out_count
    assert owner_sql(client.db, "SELECT row_label, seat_number FROM seat WHERE id = %s", (seat,)) == [("C", 12)]


def test_no_route_anywhere_has_a_cancel_or_refund_segment(client):
    segments = {seg for r in routes(client.app) for seg in r.path.split("/")}
    assert not {s for s in segments if s in ("cancel", "refund")}


def _as(client, user_id: int, role: str) -> None:
    """Switch the client's session cookie to another account, minted with the product's own token function."""
    from app.core.security import SESSION_COOKIE, issue_session_token
    from tests.dbkit import app_settings

    client.cookies.set(SESSION_COOKIE, issue_session_token(user_id=user_id, role=role, password_version=1,
                                                           now=client.clock.now(), settings=app_settings(client.db)))


def test_the_customer_booking_still_renders_the_retired_seat(cached_client):
    c = cached_client
    sign_in(c)
    hall, seat, category = _hall(c.db)
    existing = make_showtime(c.db, hall, make_movie(c.db), "2026-11-01T10:00:00Z", "2026-11-01T12:00:00Z")
    customer = insert_user(c.db, role="customer")
    ref = new_reference()  # a valid stored reference, check character included
    insert_booking(c.db, user_id=customer, reference=ref,
                   showtime={"showtime_id": existing, "seat_id": seat, "seat_category_id": category}, price_paise=25000)
    _as(c, customer, "customer")
    before = c.get(f"/api/me/bookings/FR-{ref[:4]}-{ref[4:]}")
    assert before.status_code == 200, before.text
    _as(c, insert_user(c.db, role="admin"), "admin")
    assert c.patch(f"/api/admin/seats/{seat}", json={"is_active": False}).status_code == 200
    _as(c, customer, "customer")
    after = c.get(f"/api/me/bookings/FR-{ref[:4]}-{ref[4:]}")
    assert after.status_code == 200, after.text
    assert [s["seat_label"] for s in after.json()["seats"]] == ["C12"]  # row_label C, seat_number 12
    assert after.json()["seats"] == before.json()["seats"]

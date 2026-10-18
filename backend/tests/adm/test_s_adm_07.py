"""S-ADM-07 - a hall's seat identity freezes the moment any showtime exists on it (P-ADM-14)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.deps import CurrentUser
from app.db import async_url
from app.domain.admin import halls
from app.domain.admin.halls import LayoutFrozen
from tests.adm.kit import (body_fields, client, count, make_category, make_movie, make_screen, make_seat,  # noqa: F401
                           make_showtime, routes, sign_in)
from tests.dbkit import insert_booking, insert_user
from tests.xct._support import rg

RENUMBER = ("Seat C12 cannot be renumbered. This hall has showtimes, and a seat number is what a past customer's ticket "
            "says. You can add a seat, or take a seat out of service.")
RECATEGORISE = ("Seat C12 cannot be moved to a different category. This hall has showtimes, and its seats are already "
                "priced. You can add a seat, or take a seat out of service.")
REMOVE = ("Seat C12 cannot be removed. This hall has showtimes, and removing a seat would break the record of who booked "
          "it. Take it out of service instead.")


def _frozen_hall(db, starts="2026-09-04T13:00:00Z", ends="2026-09-04T15:28:00Z"):
    hall, category = make_screen(db), make_category(db)
    seat = make_seat(db, hall, "C12", category, grid=(3, 12))
    make_seat(db, hall, "C13", category, grid=(3, 13))
    make_showtime(db, hall, make_movie(db), starts, ends)
    return hall, seat, category


def _assert_frozen(r, hall, seat, message):
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, "LAYOUT_FROZEN", message)
    details = r.json()["error"]["details"]
    assert set(details) == {"screen_id", "seat_id", "showtime_count", "frozen_fields"}
    assert (details["screen_id"], details["seat_id"], details["showtime_count"]) == (hall, seat, 1)
    assert details["frozen_fields"] == ["row_label", "seat_number", "seat_category_id"]


def test_frozen_fields_and_delete_are_409_with_their_sentences_and_no_audit_row(client):
    sign_in(client)
    hall, seat, _ = _frozen_hall(client.db)
    other = make_category(client.db)
    audits = count(client.db, "audit_log")
    _assert_frozen(client.patch(f"/api/admin/seats/{seat}", json={"row_label": "D"}), hall, seat, RENUMBER)
    _assert_frozen(client.patch(f"/api/admin/seats/{seat}", json={"seat_number": 99}), hall, seat, RENUMBER)
    _assert_frozen(client.patch(f"/api/admin/seats/{seat}", json={"seat_category_id": other}), hall, seat, RECATEGORISE)
    _assert_frozen(client.delete(f"/api/admin/seats/{seat}"), hall, seat, REMOVE)
    assert count(client.db, "audit_log") == audits
    assert count(client.db, "seat", "id = %s", (seat,)) == 1


def test_in_the_same_state_grid_service_add_and_rename_stay_permitted(client):
    sign_in(client)
    hall, seat, category = _frozen_hall(client.db)
    assert client.patch(f"/api/admin/seats/{seat}", json={"grid_row": 4, "grid_col": 20}).status_code == 200
    assert client.patch(f"/api/admin/seats/{seat}", json={"is_active": False}).status_code == 200
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [
        {"row_label": "C", "seat_number": 15, "grid_row": 3, "grid_col": 15, "seat_category_id": category}]})
    assert r.status_code == 201
    assert client.patch(f"/api/admin/screens/{hall}", json={"version": 1, "name": "Frozen but renamed"}).status_code == 200


def test_a_past_unbooked_showtime_freezes_exactly_like_a_future_sold_out_one(client):
    sign_in(client)
    hall, seat, _ = _frozen_hall(client.db, "2020-01-01T10:00:00Z", "2020-01-01T12:00:00Z")
    assert count(client.db, "booking_seat", "showtime_id IN (SELECT id FROM showtime WHERE screen_id = %s)", (hall,)) == 0
    _assert_frozen(client.patch(f"/api/admin/seats/{seat}", json={"row_label": "D"}), hall, seat, RENUMBER)


def test_a_future_sold_out_showtime_refuses_identically(client):
    sign_in(client)
    hall, seat, category = _frozen_hall(client.db, "2020-01-01T10:00:00Z", "2020-01-01T12:00:00Z")
    past_body = client.patch(f"/api/admin/seats/{seat}", json={"row_label": "D"}).json()
    hall2, category2 = make_screen(client.db), make_category(client.db)
    seats = [make_seat(client.db, hall2, label, category2, grid=(3, n)) for n, label in ((12, "C12"), (13, "C13"))]
    future = make_showtime(client.db, hall2, make_movie(client.db), "2027-01-01T10:00:00Z", "2027-01-01T12:00:00Z")
    buyer = insert_user(client.db, role="customer")
    for seat_id, ref in zip(seats, ("FRHJKMNP", "FRJKMNPQ")):
        insert_booking(client.db, user_id=buyer, reference=ref, price_paise=25000,
                       showtime={"showtime_id": future, "seat_id": seat_id, "seat_category_id": category2})
    assert count(client.db, "booking_seat", "showtime_id = %s", (future,)) == count(client.db, "showtime_seat", "showtime_id = %s", (future,))
    sold_body = client.patch(f"/api/admin/seats/{seats[0]}", json={"row_label": "D"}).json()
    for body in (past_body, sold_body):
        body["error"].pop("request_id")
        body["error"]["details"].pop("screen_id")
        body["error"]["details"].pop("seat_id")
    assert past_body == sold_body


@pytest.mark.anyio
async def test_the_domain_function_raises_layout_frozen_with_no_http_request(migrated_db):
    hall, seat, _ = _frozen_hall(migrated_db)
    engine = create_async_engine(async_url(migrated_db.app_url))
    try:
        async with engine.connect() as conn:
            from datetime import datetime, timezone
            actor = CurrentUser(id=1, email="x@example.invalid", role="admin", password_version=1)
            with pytest.raises(LayoutFrozen) as exc:
                await halls.edit_seat(conn, actor, seat, {"row_label": "D"}, datetime(2026, 9, 1, tzinfo=timezone.utc))
    finally:
        await engine.dispose()
    assert (exc.value.screen_id, exc.value.seat_id, exc.value.showtime_count) == (hall, seat, 1)


def test_the_check_is_not_in_the_handler():
    assert rg("showtime_count|LAYOUT_FROZEN", "backend/app/api/admin") == []


def test_exactly_one_route_accepts_row_label_and_it_is_patch_seat(client):
    accepting = [(sorted(r.methods), r.path) for r in routes(client.app) if "row_label" in body_fields(r)
                 and r.path != "/api/admin/screens/{screen_id}/seats"]
    # EP-ADM-19's batch carries row_label INSIDE its seats array, not as a field of its body model.
    assert accepting == [(["PATCH"], "/api/admin/seats/{seat_id}")]
    assert all("row_label" not in body_fields(r) for r in routes(client.app) if r.path == "/api/admin/screens/{screen_id}/seats")

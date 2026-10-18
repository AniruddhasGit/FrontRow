"""S-ADM-14 - a stale admin write is refused, and a write that changes nothing writes nothing (P-ADM-12).

NOT covered: the poster upload's multipart version part (EP-ADM-05, Phase 6) and the five forms'
captured request bodies (no frontend test runner exists).
"""

from __future__ import annotations

from tests.adm.kit import (body_fields, client, count, make_category, make_cinema, make_movie, make_screen, make_seat,  # noqa: F401
                           make_seats, make_showtime, routes, sign_in)
from tests.dbkit import owner_sql

STALE_HALL = ("This hall was changed by someone else while you were editing. Reload to see the current details, then make "
              "your change again. Nothing you typed has been saved.")


def test_exactly_five_tables_carry_version_and_patch_seat_accepts_none(client):
    tables = {r[0] for r in owner_sql(client.db, "SELECT table_name FROM information_schema.columns WHERE "
                                                 "table_schema = 'public' AND column_name = 'version'")}
    assert tables == {"movie", "showtime", "screen", "seat_category", "cinema"}
    patch_seat = next(r for r in routes(client.app) if r.path == "/api/admin/seats/{seat_id}" and "PATCH" in r.methods)
    assert "version" not in body_fields(patch_seat) and body_fields(patch_seat)


def test_every_admin_get_that_feeds_a_form_returns_version(client):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 1)
    make_category(client.db)
    make_showtime(client.db, hall, make_movie(client.db), "2026-09-04T13:00:00Z", "2026-09-04T14:00:00Z")
    for path, params in (("/api/admin/cinemas", None), ("/api/admin/screens", None), ("/api/admin/seat-categories", None),
                         ("/api/admin/showtimes", {"screen_id": hall, "date": "2026-09-04"})):
        items = client.get(path, params=params).json()["items"]
        assert items and all(isinstance(i["version"], int) for i in items), path


def test_no_version_is_422_and_a_stale_one_is_409_and_neither_writes(client):
    sign_in(client)
    hall = make_screen(client.db, name="Versioned hall")
    audits = count(client.db, "audit_log")
    r = client.patch(f"/api/admin/screens/{hall}", json={"name": "No version"})
    assert (r.status_code, r.json()["error"]["message"]) == (422, "This form is out of date. Reload the page and make the change again.")
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 9, "name": "Stale"})
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, "VERSION_CONFLICT", STALE_HALL)
    assert owner_sql(client.db, "SELECT name, version FROM screen WHERE id = %s", (hall,)) == [("Versioned hall", 1)]
    assert count(client.db, "audit_log") == audits
    assert client.patch(f"/api/admin/screens/{hall}", json={"version": 1, "name": "Fresh"}).json()["version"] == 2


def test_the_order_is_version_then_validation_then_no_op_then_write(client):
    sign_in(client)
    hall = make_screen(client.db, name="Order hall")
    owner_sql(client.db, "UPDATE screen SET version = 4 WHERE id = %s", (hall,))
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 3, "name": "Order hall"})
    assert r.status_code == 409  # identical fields, stale version: still refused
    long_name = "L" * 61
    owner_sql(client.db, "UPDATE screen SET name = %s WHERE id = %s", (long_name, hall))
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 4, "name": long_name})
    assert r.status_code == 422  # invalid even though it is what is stored
    owner_sql(client.db, "UPDATE screen SET name = 'Order hall' WHERE id = %s", (hall,))
    audits = count(client.db, "audit_log")
    before = owner_sql(client.db, "SELECT * FROM screen WHERE id = %s", (hall,))
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 4, "name": "Order hall", "is_active": True})
    assert r.status_code == 200 and r.json()["version"] == 4
    assert owner_sql(client.db, "SELECT * FROM screen WHERE id = %s", (hall,)) == before
    assert count(client.db, "audit_log") == audits


def test_two_fields_one_changed_writes_one_row_naming_that_change(client):
    sign_in(client)
    hall = make_screen(client.db, name="Partial hall")
    audits = count(client.db, "audit_log")
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 1, "name": "Partial hall", "is_active": False})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert count(client.db, "audit_log") == audits + 1
    assert owner_sql(client.db, "SELECT action FROM audit_log WHERE entity_type = 'screen' AND entity_id = %s", (hall,)) == [
        ("screen.deactivated",)]


def test_the_seat_exemption_is_scoped_to_is_active(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    seat = make_seat(client.db, hall, "C12", category, grid=(3, 12))
    r = client.patch(f"/api/admin/seats/{seat}", json={"is_active": True})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "LAYOUT_FROZEN")
    audits = count(client.db, "audit_log")
    assert client.patch(f"/api/admin/seats/{seat}", json={"grid_row": 3}).status_code == 200
    assert count(client.db, "audit_log") == audits

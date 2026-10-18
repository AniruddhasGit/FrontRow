"""S-ADM-05 - create, rename and list halls (P-ADM-13, EP-ADM-15/16/17)."""

from __future__ import annotations

from tests.adm.kit import audit_rows, client, count, make_cinema, make_movie, make_screen, make_seats, make_showtime, sign_in  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import mounted_routes


def test_create_returns_201_in_service_unfrozen_version_1_and_one_screen_created_row(client):
    admin = sign_in(client)
    cinema = make_cinema(client.db)
    r = client.post("/api/admin/screens", json={"cinema_id": cinema, "name": "  Screen Seven  "})
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["is_active"], body["has_showtimes"], body["version"], body["name"]) == (True, False, 1, "Screen Seven")
    assert audit_rows(client.db, "entity_type = 'screen' AND entity_id = %s", (body["id"],)) == [
        ("screen.created", "screen", body["id"], None, {"cinema_id": cinema, "name": "Screen Seven", "is_active": True}, admin)]


def test_a_duplicate_name_and_a_case_variant_are_refused_and_nothing_is_written(client):
    sign_in(client)
    cinema = make_cinema(client.db)
    assert client.post("/api/admin/screens", json={"cinema_id": cinema, "name": "Screen 3"}).status_code == 201
    before = count(client.db, "screen")
    for name in ("Screen 3", "screen 3", " SCREEN 3 "):
        r = client.post("/api/admin/screens", json={"cinema_id": cinema, "name": name})
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_FAILED", name
        assert r.json()["error"]["message"] == "A hall with that name already exists."
    assert count(client.db, "screen") == before


def test_name_bounds_0_and_61_refused_60_accepted(client):
    sign_in(client)
    cinema = make_cinema(client.db)
    for name in ("   ", "x" * 61, " " + "y" * 61 + " "):
        r = client.post("/api/admin/screens", json={"cinema_id": cinema, "name": name})
        assert r.status_code == 422 and r.json()["error"]["message"] == "Enter a hall name of 1 to 60 characters."
    assert client.post("/api/admin/screens", json={"cinema_id": cinema, "name": " " + "z" * 60 + " "}).status_code == 201


def test_rename_increments_version_by_one_writes_screen_updated_and_works_on_a_hall_with_showtimes(client):
    sign_in(client)
    screen = make_screen(client.db)
    make_seats(client.db, screen, 3)
    make_showtime(client.db, screen, make_movie(client.db), "2026-09-04T13:00:00Z", "2026-09-04T15:28:00Z")
    assert count(client.db, "showtime", "screen_id = %s", (screen,)) > 0
    r = client.patch(f"/api/admin/screens/{screen}", json={"version": 1, "name": "Renamed hall"})
    assert r.status_code == 200, r.text
    assert (r.json()["version"], r.json()["name"], r.json()["has_showtimes"]) == (2, "Renamed hall", True)
    rows = audit_rows(client.db, "entity_type = 'screen' AND entity_id = %s", (screen,))
    assert [row[0] for row in rows] == ["screen.updated"]
    assert rows[0][4] == {"name": "Renamed hall"}


def test_list_returns_every_hall_active_and_not_ordered_name_then_id_with_every_field(client):
    sign_in(client)
    cinema = make_cinema(client.db)
    a = make_screen(client.db, cinema, name="AAA list hall", active=False)
    b = make_screen(client.db, cinema, name="AAB list hall")
    make_seats(client.db, b, 4)
    owner_sql(client.db, "UPDATE seat SET is_active = false WHERE id = (SELECT min(id) FROM seat WHERE screen_id = %s)", (b,))
    r = client.get("/api/admin/screens")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert ids.index(a) < ids.index(b)  # name ASC: "AAA..." before "AAB..."
    mine = {i["id"]: i for i in items if i["id"] in (a, b)}
    assert set(mine[a]) == {"id", "cinema_id", "name", "is_active", "seat_count_total", "seat_count_in_service",
                            "has_showtimes", "version"}
    assert (mine[a]["is_active"], mine[b]["is_active"]) == (False, True)
    assert (mine[b]["seat_count_total"], mine[b]["seat_count_in_service"], mine[b]["has_showtimes"]) == (4, 3, False)


def test_no_delete_route_for_a_hall_and_the_request_is_405_with_the_generic_sentence(client):
    sign_in(client)
    assert ("DELETE", "/api/admin/screens/{screen_id}") not in mounted_routes(client.app)
    screen = make_screen(client.db)
    before = count(client.db, "screen")
    r = client.delete(f"/api/admin/screens/{screen}")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert r.json()["error"]["message"] == "That action is not available. Nothing was changed."
    assert count(client.db, "screen") == before

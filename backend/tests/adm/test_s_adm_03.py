"""S-ADM-03 - read and edit the venue (P-ADM-25, EP-ADM-28/29)."""

from __future__ import annotations

from tests.adm.kit import audit_rows, client, count, make_cinema, make_screen, sign_in  # noqa: F401
from tests.xct._support import mounted_routes

GENERIC_405 = "That action is not available. Nothing was changed."


def test_list_is_ordered_and_carries_every_field(client):
    sign_in(client)
    b = make_cinema(client.db, name="BBB venue")
    a = make_cinema(client.db, name="AAA venue")
    make_screen(client.db, a)
    items = client.get("/api/admin/cinemas").json()["items"]
    ids = [i["id"] for i in items]
    assert ids.index(a) < ids.index(b)
    row = next(i for i in items if i["id"] == a)
    assert set(row) >= {"id", "name", "timezone", "screen_count", "version"}
    assert (row["screen_count"], row["timezone"], row["version"]) == (1, "Asia/Kolkata", 1)


def test_rename_with_matching_version_is_200_version_plus_one_and_one_cinema_updated_row(client):
    sign_in(client)
    c = make_cinema(client.db)
    r = client.patch(f"/api/admin/cinemas/{c}", json={"version": 1, "name": "DEMO CINEMA RENAMED"})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert [x[0] for x in audit_rows(client.db, "entity_type = 'cinema' AND entity_id = %s", (c,))] == ["cinema.updated"]


def test_name_and_zone_in_one_request_write_two_rows(client):
    sign_in(client)
    c = make_cinema(client.db)
    r = client.patch(f"/api/admin/cinemas/{c}", json={"version": 1, "name": "Both changed", "timezone": "Asia/Dubai"})
    assert r.status_code == 200
    assert [x[0] for x in audit_rows(client.db, "entity_type = 'cinema' AND entity_id = %s", (c,))] == [
        "cinema.updated", "cinema.timezone_changed"]


def test_an_unknown_zone_a_121_character_name_and_a_taken_name_are_422_with_nothing_written(client):
    sign_in(client)
    make_cinema(client.db, name="Taken Venue")
    c = make_cinema(client.db)
    audits = count(client.db, "audit_log")
    cases = [({"timezone": "Asia/Atlantis"}, "That is not a time zone this system recognises. Enter an IANA zone name, "
                                             "such as Asia/Kolkata."),
             ({"name": " " + "n" * 121 + " "}, "Enter a venue name of 1 to 120 characters."),
             ({"name": "  taken venue "}, "A venue with that name already exists.")]
    for body, message in cases:
        r = client.patch(f"/api/admin/cinemas/{c}", json={"version": 1, **body})
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (422, "VALIDATION_FAILED", message)
    assert count(client.db, "audit_log") == audits
    assert count(client.db, "cinema", "id = %s AND version = 1", (c,)) == 1


def test_a_stale_version_is_409_and_writes_nothing(client):
    sign_in(client)
    c = make_cinema(client.db)
    audits = count(client.db, "audit_log")
    r = client.patch(f"/api/admin/cinemas/{c}", json={"version": 7, "name": "Never written"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    assert count(client.db, "audit_log") == audits
    assert count(client.db, "cinema", "id = %s AND name = 'Never written'", (c,)) == 0


def test_no_create_and_no_delete_route_and_both_answer_405_from_the_global_handler(client):
    sign_in(client)
    mounted = mounted_routes(client.app)
    assert ("POST", "/api/admin/cinemas") not in mounted
    assert ("DELETE", "/api/admin/cinemas/{cinema_id}") not in mounted
    c = make_cinema(client.db)
    for r in (client.post("/api/admin/cinemas", json={"name": "x", "timezone": "UTC"}),
              client.delete(f"/api/admin/cinemas/{c}")):
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (405, "METHOD_NOT_ALLOWED", GENERIC_405)


def test_a_hall_without_cinema_id_is_422_and_never_defaulted(client):
    sign_in(client)
    make_cinema(client.db)
    before = count(client.db, "screen")
    r = client.post("/api/admin/screens", json={"name": "Orphan hall"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")
    assert count(client.db, "screen") == before

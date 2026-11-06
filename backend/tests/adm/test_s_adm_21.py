"""S-ADM-21 - create and list the lookup vocabularies a film is built from (P-ADM-23, EP-ADM-25/26).

The SCR-ADM-02 empty-vocabulary clause is asserted by the render test frontend/src/features/admin/films.test.mjs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.adm.kit import (audit_rows, body_fields, client, count, make_cinema, make_screen, make_showtime,  # noqa: F401
                           new_film, routes, sign_in)
from tests.dbkit import app_settings, create_database, drop_database, owner_sql
from tests.test_health import ok_probe

KINDS = ("language", "certification", "genre", "format")


def test_exactly_the_four_kinds_create_and_a_fifth_is_an_address_that_does_not_exist(client):
    admin = sign_in(client)
    for kind in KINDS:
        r = client.post(f"/api/admin/lookups/{kind}", json={"name": f"Created {kind}"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["is_active"] is True and body["name"] == f"Created {kind}"
        assert set(body) == {"id", "name", "is_active", "created_at"}
        rows = audit_rows(client.db, "entity_type = %s AND entity_id = %s", (kind, body["id"]))
        assert rows == [(f"{kind}.created", kind, body["id"], None, {"name": f"Created {kind}"}, admin)]
    r = client.post("/api/admin/lookups/studio", json={"name": "Studio X"})
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (404, "NOT_FOUND", "That page does not exist.")


def test_the_name_bound_is_1_to_60_after_trimming(client):
    sign_in(client)
    for bad in ("", "   ", "x" * 61):
        r = client.post("/api/admin/lookups/language", json={"name": bad})
        assert (r.status_code, r.json()["error"]["message"]) == (422, "Enter a name of 1 to 60 characters."), bad
    assert client.post("/api/admin/lookups/language", json={"name": "  " + "y" * 60 + "  "}).status_code == 201


def test_a_duplicate_is_refused_with_the_sentence_for_an_active_and_for_a_withdrawn_entry(client):
    sign_in(client)
    first = client.post("/api/admin/lookups/certification", json={"name": "Dup Rating"}).json()
    r = client.post("/api/admin/lookups/certification", json={"name": "  dup rating "})
    assert (r.status_code, r.json()["error"]["message"]) == (422, "That name is already on this list. Every entry needs its own name.")
    assert client.patch(f"/api/admin/lookups/certification/{first['id']}", json={"is_active": False}).status_code == 200
    r = client.post("/api/admin/lookups/certification", json={"name": "DUP RATING"})
    assert (r.status_code, r.json()["error"]["message"]) == (
        422, "That name is already on this list, on an entry that has been withdrawn. Restore that entry instead of adding it again.")
    assert count(client.db, "certification", "lower(name) = 'dup rating'") == 1


def test_one_name_in_two_vocabularies_is_two_rows_and_the_admins_case_is_kept(client):
    sign_in(client)
    g = client.post("/api/admin/lookups/genre", json={"name": "  Drama  "})
    f = client.post("/api/admin/lookups/format", json={"name": "Drama"})
    assert g.status_code == f.status_code == 201
    assert owner_sql(client.db, "SELECT name FROM genre WHERE id = %s", (g.json()["id"],)) == [("Drama",)]
    assert owner_sql(client.db, "SELECT name FROM format WHERE id = %s", (f.json()["id"],)) == [("Drama",)]
    listed = client.get("/api/admin/lookups/genre").json()["items"]
    assert "Drama" in [i["name"] for i in listed] and "drama" not in [i["name"] for i in listed]


def test_is_active_or_id_in_the_body_is_400_and_nothing_is_created(client):
    sign_in(client)
    before = count(client.db, "language")
    for extra in ({"is_active": True}, {"id": 900}):
        r = client.post("/api/admin/lookups/language", json={"name": "Never made", **extra})
        assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID")
    assert count(client.db, "language") == before


def test_the_list_shape_order_default_and_reference_count_counting_every_referencing_row(client):
    sign_in(client)
    lang = client.post("/api/admin/lookups/language", json={"name": "Counted language"}).json()["id"]
    gone = client.post("/api/admin/lookups/language", json={"name": "Aaa withdrawn"}).json()["id"]
    client.patch(f"/api/admin/lookups/language/{gone}", json={"is_active": False})
    draft = new_film(client, language_id=lang)
    published = new_film(client, language_id=lang)
    owner_sql(client.db, "UPDATE movie SET published_at = now() WHERE id = %s", (published["id"],))

    def item(include: str | None = None) -> list[dict]:
        params = {} if include is None else {"include_withdrawn": include}
        r = client.get("/api/admin/lookups/language", params=params)
        assert r.status_code == 200 and r.json()["kind"] == "language"
        return r.json()["items"]

    items = item()
    assert all(set(i) == {"id", "name", "is_active", "created_at", "reference_count"} for i in items)
    assert [(i["name"], i["id"]) for i in items] == sorted((i["name"], i["id"]) for i in items)
    assert gone not in [i["id"] for i in items] and gone in [i["id"] for i in item("true")]
    assert [i["reference_count"] for i in items if i["id"] == lang] == [2]
    # A third film whose only showtime is already past its sales cut-off still holds the entry up.
    third = new_film(client, language_id=lang)
    make_showtime(client.db, make_screen(client.db, make_cinema(client.db)), third["id"], "2026-01-01T10:00:00Z",
                  "2026-01-01T12:00:00Z", with_seats=False)
    assert [i["reference_count"] for i in item() if i["id"] == lang] == [3]
    assert draft["published_at"] is None
    assert client.get("/api/admin/lookups/language", params={"include_withdrawn": "yes"}).status_code == 422


def test_no_delete_route_and_no_route_that_renames(client):
    sign_in(client)
    lang = client.post("/api/admin/lookups/language", json={"name": "Undeletable"}).json()["id"]
    for path in ("/api/admin/lookups/language", f"/api/admin/lookups/language/{lang}"):
        r = client.delete(path)
        assert (r.status_code, r.json()["error"]["code"]) == (405, "METHOD_NOT_ALLOWED")
    lookup_routes = [r for r in routes(client.app) if r.path.startswith("/api/admin/lookups")]
    assert {(m, r.path) for r in lookup_routes for m in r.methods} == {
        ("GET", "/api/admin/lookups/{kind}"), ("POST", "/api/admin/lookups/{kind}"), ("PATCH", "/api/admin/lookups/{kind}/{id}")}
    patch = [r for r in lookup_routes if "PATCH" in r.methods][0]
    assert body_fields(patch) == {"is_active"}  # no name: nothing can rename an entry


def test_an_unseeded_database_lists_nothing_for_all_four_kinds(clock):
    fresh = create_database(migrate=True)
    try:
        app = create_app(app_settings(fresh), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
        with TestClient(app, raise_server_exceptions=False) as c:
            c.db, c.clock = fresh, clock
            sign_in(c)
            for kind in KINDS:
                r = c.get(f"/api/admin/lookups/{kind}")
                assert (r.status_code, r.json()["items"]) == (200, []), kind
    finally:
        drop_database(fresh)

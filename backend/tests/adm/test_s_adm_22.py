"""S-ADM-22 - withdraw a lookup entry from future use, and restore it (P-ADM-24, EP-ADM-27)."""

from __future__ import annotations

from tests.adm.kit import (client, count, make_cinema, make_lookup, make_screen, new_film, owner_sql, sign_in,  # noqa: F401
                           strip_request_id)

FILM_WINDOW = ("2026-10-01T00:00:00Z", "2026-10-30T00:00:00Z")  # the injected clock (2026-10-18) is inside it


def _publish_directly(db, movie_id: int) -> None:
    owner_sql(db, "UPDATE movie SET published_at = '2026-10-02T00:00:00Z', display_from = %s, display_until = %s WHERE id = %s",
              (*FILM_WINDOW, movie_id))


def test_withdraw_and_restore_write_one_audit_row_each_in_the_same_transaction(client):
    admin = sign_in(client)
    for kind in ("language", "certification", "genre", "format"):
        entry = make_lookup(client.db, kind)
        r = client.patch(f"/api/admin/lookups/{kind}/{entry}", json={"is_active": False})
        assert (r.status_code, r.json()["is_active"]) == (200, False)
        rid = r.headers["x-request-id"]
        r2 = client.patch(f"/api/admin/lookups/{kind}/{entry}", json={"is_active": True})
        assert (r2.status_code, r2.json()["is_active"]) == (200, True)
        rows = owner_sql(client.db, "SELECT action, before, after, actor_user_id, request_id FROM audit_log "
                                    "WHERE entity_type = %s AND entity_id = %s ORDER BY id", (kind, entry))
        assert rows == [(f"{kind}.withdrawn", {"is_active": True}, {"is_active": False}, admin, rid),
                        (f"{kind}.restored", {"is_active": False}, {"is_active": True}, admin, r2.headers["x-request-id"])]


def test_a_withdrawn_entry_leaves_the_default_list_and_every_film_already_using_it_is_untouched(client):
    sign_in(client)
    make_screen(client.db, make_cinema(client.db))
    lang = client.post("/api/admin/lookups/language", json={"name": "Hnidi"}).json()["id"]
    film = new_film(client, language_id=lang)
    _publish_directly(client.db, film["id"])
    assert client.patch(f"/api/admin/lookups/language/{lang}", json={"is_active": False}).status_code == 200
    assert lang not in [i["id"] for i in client.get("/api/admin/lookups/language").json()["items"]]
    assert lang in [i["id"] for i in client.get("/api/admin/lookups/language?include_withdrawn=true").json()["items"]]
    client.cookies.clear()  # a guest, on the customer surface
    one = client.get(f"/api/movies/{film['id']}")
    assert one.status_code == 200 and one.json()["language"]["name"] == "Hnidi"
    listed = client.get(f"/api/movies?language_id={lang}").json()["movies"]
    assert film["id"] in [m["id"] for m in listed]


def test_name_in_the_body_is_400_and_the_name_is_unchanged(client):
    sign_in(client)
    entry = make_lookup(client.db, "genre", name="Keep me")
    r = client.patch(f"/api/admin/lookups/genre/{entry}", json={"is_active": False, "name": "Renamed"})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID")
    assert r.json()["error"]["message"] == "That request could not be understood. This address changes only whether an entry is in use."
    assert owner_sql(client.db, "SELECT name, is_active FROM genre WHERE id = %s", (entry,)) == [("Keep me", True)]


def test_is_active_missing_or_not_a_boolean_is_422(client):
    sign_in(client)
    entry = make_lookup(client.db, "format")
    for body in ({}, {"is_active": "yes"}):
        r = client.patch(f"/api/admin/lookups/format/{entry}", json=body)
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
            422, "VALIDATION_FAILED", "Choose whether this entry is in use."), body


def test_the_value_already_held_is_200_byte_identical_and_writes_no_audit_row(client):
    sign_in(client)
    entry = make_lookup(client.db, "certification")
    before = owner_sql(client.db, "SELECT * FROM certification WHERE id = %s", (entry,))
    audits = count(client.db, "audit_log")
    r = client.patch(f"/api/admin/lookups/certification/{entry}", json={"is_active": True})
    assert (r.status_code, r.json()["is_active"]) == (200, True)
    assert owner_sql(client.db, "SELECT * FROM certification WHERE id = %s", (entry,)) == before
    assert count(client.db, "audit_log") == audits


def test_an_unknown_kind_and_an_unknown_id_answer_the_same_404(client):
    sign_in(client)
    a = client.patch("/api/admin/lookups/studio/1", json={"is_active": False})
    b = client.patch("/api/admin/lookups/language/999999", json={"is_active": False})
    assert a.status_code == b.status_code == 404
    assert a.json()["error"]["message"] == "That page does not exist."
    assert strip_request_id(a.json()) == strip_request_id(b.json())
    r = client.delete("/api/admin/lookups/language/1")
    assert (r.status_code, r.json()["error"]["code"]) == (405, "METHOD_NOT_ALLOWED")


def test_correcting_a_typo_is_two_actions_and_both_stay_on_the_record(client):
    sign_in(client)
    # Ids far from anything else this module audits, so the AC's bare `WHERE entity_id = :id` counts one entity only.
    typo = owner_sql(client.db, "INSERT INTO language (id, name, is_active) OVERRIDING SYSTEM VALUE VALUES (4004, 'Hnidi2', true) "
                                "RETURNING id")[0][0]
    film = new_film(client, language_id=typo)
    assert client.patch(f"/api/admin/lookups/language/{typo}", json={"is_active": False}).status_code == 200
    fixed = client.post("/api/admin/lookups/language", json={"name": "Hindi2"}).json()["id"]
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": film["version"], "language_id": fixed})
    assert r.status_code == 200 and r.json()["language"]["name"] == "Hindi2"
    assert count(client.db, "audit_log", "entity_id = %s", (typo,)) == 1
    assert owner_sql(client.db, "SELECT action, before, after FROM audit_log WHERE entity_type = 'language' AND entity_id = %s",
                     (typo,)) == [("language.withdrawn", {"is_active": True}, {"is_active": False})]
    assert owner_sql(client.db, "SELECT before, after FROM audit_log WHERE action = 'movie.updated' AND entity_id = %s",
                     (film["id"],)) == [({"language_id": typo}, {"language_id": fixed})]

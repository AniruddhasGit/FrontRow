"""CR-008 T12: the admin film editor sets the full details (release date, cast, crew), validated and audited."""

from __future__ import annotations

from tests.adm.kit import client, new_film, owner_sql, sign_in  # noqa: F401


def test_the_details_are_optional_editable_validated_and_audited(client):
    sign_in(client)
    film = new_film(client)
    assert (film["release_date"], film["cast_members"], film["crew_members"]) == (None, None, None)
    r = client.patch(f"/api/admin/movies/{film['id']}", json={
        "version": film["version"], "release_date": "2026-12-04", "cast_members": "  Mira Hale: Ines\nTomas Reed  ",
        "crew_members": "Ana Ruiz: Director"})
    assert r.status_code == 200, r.text
    edited = r.json()
    assert (edited["release_date"], edited["cast_members"], edited["crew_members"]) == \
        ("2026-12-04", "Mira Hale: Ines\nTomas Reed", "Ana Ruiz: Director")
    before, after = owner_sql(client.db, "SELECT before, after FROM audit_log WHERE action = 'movie.updated' AND entity_id = %s",
                              (film["id"],))[0]
    assert before["release_date"] is None and after["release_date"] == "2026-12-04"
    for bad in ({"release_date": "4 Dec"}, {"release_date": "2026-02-30"}, {"release_date": 20261204},
                {"cast_members": "x" * 4001}, {"crew_members": ["a"]}):
        r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": edited["version"], **bad})
        assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), bad
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": edited["version"], "release_date": None, "cast_members": ""})
    assert (r.json()["release_date"], r.json()["cast_members"]) == (None, None)

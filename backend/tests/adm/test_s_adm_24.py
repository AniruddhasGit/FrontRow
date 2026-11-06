"""S-ADM-24 - edit a film under optimistic concurrency (P-ADM-02, EP-ADM-04)."""

from __future__ import annotations

import re

from tests.adm.kit import (cached_client, client, count, film_body, make_category, make_cinema, make_screen,  # noqa: F401
                           make_seat, make_showtime, movie_row, new_film, owner_sql, sign_in, tag)
from tests.brw.kit import book_seat

# S-ADM-23's 422 cases, replayed as a PATCH.
S_ADM_23_422 = [{"title": "   "}, {"title": "t" * 201}, {"synopsis": "s" * 4001}, {"runtime_minutes": 0},
                {"runtime_minutes": -1}, {"runtime_minutes": 148.5}, {"runtime_minutes": None}, {"language_id": 987654},
                {"certification_id": 987654}, {"genre_ids": []}, {"genre_ids": list(range(1, 12))}, {"genre_ids": [987654]}]


def test_a_matching_version_applies_increments_by_one_and_audits_only_the_changed_keys(client):
    admin = sign_in(client)
    film = new_film(client)
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "synopsis": "A new synopsis.",
                                                                "title": film["title"]})
    assert (r.status_code, r.json()["version"], r.json()["synopsis"]) == (200, 2, "A new synopsis.")
    assert owner_sql(client.db, "SELECT action, before, after, actor_user_id FROM audit_log WHERE action = 'movie.updated' "
                                "AND entity_id = %s", (film["id"],)) == [
        ("movie.updated", {"synopsis": "Demonstration film."}, {"synopsis": "A new synopsis."}, admin)]


def test_a_stale_version_is_409_with_the_row_and_the_audit_log_unchanged_and_no_version_is_422(client):
    sign_in(client)
    film = new_film(client)
    row, audits = movie_row(client.db, film["id"]), count(client.db, "audit_log")
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 7, "title": "Changed"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"title": "Changed"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")
    assert movie_row(client.db, film["id"]) == row and count(client.db, "audit_log") == audits


def test_every_s_adm_23_bound_applies_on_the_edit(client):
    sign_in(client)
    film = new_film(client)
    row = movie_row(client.db, film["id"])
    twice = {"genre_ids": [film["genre_ids"][0]] * 2}  # the same id twice: needs a real id, so built per film
    for over in [*S_ADM_23_422, twice]:
        r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, **over})
        assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), over
    assert movie_row(client.db, film["id"]) == row


def test_an_undeclared_property_is_400(client):
    sign_in(client)
    film = new_film(client)
    for extra in ({"published_at": None}, {"poster_object_key": "x"}, {"colour": "red"}):
        r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, **extra})
        assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID"), extra


def test_replaying_the_identical_successful_request_is_409_and_changes_nothing(client):
    sign_in(client)
    film = new_film(client)
    body = {"version": 1, "title": f"DEMO MOVIE {tag()}"}
    assert client.patch(f"/api/admin/movies/{film['id']}", json=body).status_code == 200
    row = movie_row(client.db, film["id"])
    r = client.patch(f"/api/admin/movies/{film['id']}", json=body)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    assert movie_row(client.db, film["id"]) == row


def test_a_published_title_edit_is_in_the_first_listing_after_the_200_with_the_cache_on(cached_client):
    c = cached_client
    sign_in(c)
    make_screen(c.db, make_cinema(c.db))
    film = new_film(c, title="DEMO MOVIE 03")
    owner_sql(c.db, "UPDATE movie SET published_at = '2026-10-02T00:00:00Z', display_from = '2026-10-01T00:00:00Z', "
                    "display_until = '2026-10-30T00:00:00Z' WHERE id = %s", (film["id"],))
    # Prime the cache AFTER publication: the listing now holds the old title and would serve it for 60 s.
    assert "DEMO MOVIE 03" in c.get("/api/movies").text
    assert c.get("/api/movies").text == c.get("/api/movies").text
    r = c.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "title": "DEMO MOVIE 03 REVISED"})
    assert r.status_code == 200
    first = c.get("/api/movies")  # no sleep, no clock movement: the 60 s TTL has not elapsed
    titles = [m["title"] for m in first.json()["movies"] if m["id"] == film["id"]]
    assert titles == ["DEMO MOVIE 03 REVISED"]
    assert re.search(r"DEMO MOVIE 03(?! REVISED)", first.text) is None


def test_a_booking_on_the_edited_film_is_unchanged_and_points_at_it_by_foreign_key(client):
    sign_in(client)
    hall = make_screen(client.db, make_cinema(client.db))
    seats = [make_seat(client.db, hall, f"A{n}", make_category(client.db)) for n in (1, 2)]
    film = new_film(client)
    st = make_showtime(client.db, hall, film["id"], "2026-10-20T13:00:00Z", "2026-10-20T15:30:00Z")
    booking = book_seat(client.db, st, seats[0], price=25000)
    prices = "SELECT price_paise FROM booking_seat WHERE booking_id = %s ORDER BY id"
    before = owner_sql(client.db, prices, (booking,))
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "title": "Renamed", "runtime_minutes": 99})
    assert r.status_code == 200
    assert owner_sql(client.db, prices, (booking,)) == before == [(25000,)]
    fks = owner_sql(client.db, """
        SELECT k.table_name, k.column_name FROM information_schema.referential_constraints rc
        JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name
         AND k.constraint_schema = rc.constraint_schema
        WHERE rc.constraint_schema = current_schema() AND rc.unique_constraint_name = 'movie_pkey'""")
    assert ("showtime", "movie_id") in fks  # booking -> showtime -> movie: the film is referenced, never copied
    assert ("booking", "showtime_id") in owner_sql(client.db, """
        SELECT k.table_name, k.column_name FROM information_schema.referential_constraints rc
        JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name
         AND k.constraint_schema = rc.constraint_schema
        WHERE rc.constraint_schema = current_schema() AND rc.unique_constraint_name = 'showtime_pkey'""")

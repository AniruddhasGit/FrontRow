"""S-ADM-23 - create a film by hand as a draft (P-ADM-01, EP-ADM-01/02).

NOT met as written, and reported: the AC's `INSERT INTO movie\\b|Movie[(]` must hit exactly backend/app/api/admin/movies.py
and scripts/seed.py. The film insert is SQLAlchemy Core `insert(movie)` in backend/app/domain/admin/films.py (every rule
lives in app/domain/admin, FR-ADR-022), which that pattern cannot see. The intent - nothing but the admin path and the
seed inserts a movie row - is asserted below with a pattern that sees both spellings.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import create_app
from tests.adm.kit import client, count, film_body, make_lookup, new_film, owner_sql, sign_in, tag  # noqa: F401
from tests.dbkit import app_settings, create_database, drop_database
from tests.test_health import ok_probe
from tests.xct._support import rg

NAIVE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")


def test_a_create_is_a_draft_with_its_genres_and_one_audit_row_in_one_transaction(client):
    admin = sign_in(client)
    body = film_body(client.db)
    r = client.post("/api/admin/movies", json=body)
    assert r.status_code == 201, r.text
    film = r.json()
    assert (film["published_at"], film["poster_present"], film["version"]) == (None, False, 1)
    assert owner_sql(client.db, "SELECT genre_id FROM movie_genre WHERE movie_id = %s ORDER BY genre_id",
                     (film["id"],)) == [(g,) for g in sorted(body["genre_ids"])]
    rows = owner_sql(client.db, "SELECT action, before, after, actor_user_id FROM audit_log WHERE entity_type = 'movie' "
                                "AND entity_id = %s", (film["id"],))
    assert rows == [("movie.created", None, {**body, "genre_ids": sorted(body["genre_ids"])}, admin)]


def test_every_field_bound(client):
    sign_in(client)
    cases = [({"title": "   "}, 422), ({"title": "t" * 200}, 201), ({"title": "t" * 201}, 422),
             ({"synopsis": "s" * 4000}, 201), ({"synopsis": "s" * 4001}, 422),
             ({"runtime_minutes": 0}, 422), ({"runtime_minutes": -1}, 422), ({"runtime_minutes": 148.5}, 422),
             ({"language_id": 987654}, 422), ({"certification_id": 987654}, 422),
             ({"genre_ids": []}, 422), ({"genre_ids": [987654]}, 422)]
    for over, status in cases:
        r = client.post("/api/admin/movies", json=film_body(client.db, **over))
        assert r.status_code == status, (over, r.text)
        if status == 422:
            assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    missing = film_body(client.db)
    del missing["runtime_minutes"]
    r = client.post("/api/admin/movies", json=missing)
    assert (r.status_code, r.json()["error"]["message"]) == (422, "Enter the runtime in whole minutes, 1 or more.")


def test_genre_ids_hold_1_to_10_distinct_existing_entries(client):
    sign_in(client)
    genres = [make_lookup(client.db, "genre") for _ in range(11)]
    assert client.post("/api/admin/movies", json=film_body(client.db, genre_ids=genres[:10])).status_code == 201
    for bad in (genres, [genres[0], genres[0]]):
        r = client.post("/api/admin/movies", json=film_body(client.db, genre_ids=bad))
        assert (r.status_code, r.json()["error"]["message"]) == (422, "Choose at least one genre from the list.")


def test_published_at_or_poster_object_key_in_the_body_is_400_and_nothing_is_created(client):
    sign_in(client)
    before = count(client.db, "movie")
    for extra in ({"published_at": "2026-10-18T09:30:00Z"}, {"poster_object_key": "posters/1/" + "a" * 32}):
        r = client.post("/api/admin/movies", json={**film_body(client.db), **extra})
        assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID")
    assert count(client.db, "movie") == before


def test_a_title_is_not_unique(client):
    sign_in(client)
    title = f"DEMO MOVIE {tag()}"
    a, b = new_film(client, title=title), new_film(client, title=title)
    assert a["id"] != b["id"] and count(client.db, "movie", "title = %s", (title,)) == 2


def test_the_list_order_paging_and_the_two_datetime_shapes(client):
    sign_in(client)
    for _ in range(3):
        new_film(client)
    last = new_film(client)
    owner_sql(client.db, "UPDATE movie SET published_at = '2026-10-02T04:05:06Z', display_from = '2026-09-03T18:30:00Z', "
                         "display_until = '2026-10-01T18:30:00Z' WHERE id = %s", (last["id"],))
    r = client.get("/api/admin/movies")
    assert r.status_code == 200
    page = r.json()
    total = count(client.db, "movie")
    assert page["total"] == total and len(page["items"]) == min(50, total)
    stored = owner_sql(client.db, "SELECT id FROM movie ORDER BY created_at DESC, id DESC LIMIT 50")
    assert [i["id"] for i in page["items"]] == [s[0] for s in stored]
    item = [i for i in page["items"] if i["id"] == last["id"]][0]
    assert NAIVE.match(item["display_from"]) and NAIVE.match(item["display_until"])
    assert INSTANT.match(item["published_at"])
    assert (item["published"], item["window_open"]) == (True, False)  # the window lapsed on 1 Oct; the clock is 18 Oct
    assert [i["id"] for i in client.get("/api/admin/movies?limit=2&offset=1").json()["items"]] == [s[0] for s in stored[1:3]]
    assert all(i["published_at"] is None for i in client.get("/api/admin/movies?status=draft").json()["items"])
    for bad in ("limit=0", "limit=101", "offset=-1", "status=live"):
        assert client.get(f"/api/admin/movies?{bad}").status_code == 422, bad


def test_an_unseeded_database_refuses_a_film_until_each_required_vocabulary_has_a_row(clock):
    fresh = create_database(migrate=True)
    try:
        app = create_app(app_settings(fresh), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
        with TestClient(app, raise_server_exceptions=False) as c:
            c.db, c.clock = fresh, clock
            sign_in(c)
            body = {"title": "DEMO MOVIE 01", "synopsis": "", "runtime_minutes": 90, "language_id": 1, "certification_id": 1,
                    "genre_ids": [1]}
            for kind in ("language", "certification", "genre"):
                assert c.post("/api/admin/movies", json=body).status_code == 422, kind
                assert c.post(f"/api/admin/lookups/{kind}", json={"name": f"DEMO {kind.upper()} 1"}).json()["id"] == 1
            assert c.post("/api/admin/movies", json=body).status_code == 201
    finally:
        drop_database(fresh)


def test_nothing_imports_schedules_or_upserts_a_film():
    trees = ("backend/app", "backend/migrations", "frontend/src", "scripts")
    assert rg(r"tmdb|themoviedb|omdb|movie_api|external_id", *trees) == []
    # "Naming movie" is read as the movie TABLE: the seed's movie_genre join insert carries ON CONFLICT DO NOTHING
    # (scripts/seed.py, the seed lane's), and a join row is not a film (reported as an AC ambiguity).
    assert [h for h in rg(r"ON CONFLICT", *trees) if re.search(r"\bmovie\b", h[2])] == []
    assert rg(r"APScheduler|celery|crontab|schedule[.]every|EventBridge", *trees) == []


def test_only_the_admin_path_and_the_seed_insert_a_movie_row():
    # The AC's literal pattern plus the SQLAlchemy Core spelling it cannot see (see the module docstring).
    hits = {h[0] for h in rg(r"INSERT INTO movie\b|Movie[(]|insert[(]movie[)]", "backend/app", "backend/migrations", "scripts")}
    assert hits == {"backend/app/domain/admin/films.py", "scripts/seed.py"}
    assert rg(r"INSERT INTO movie\b|insert[(]movie[)]", "backend/app/workers", "backend/app/jobs") == []

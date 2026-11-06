"""S-ADM-27 - publish a film only when it is complete (P-ADM-05, EP-ADM-07)."""

from __future__ import annotations

import ast
import re
from datetime import datetime, timezone

from sqlalchemy import event

from app.api.admin.movies import Film
from tests.adm.kit import (client, count, make_cinema, make_screen, movie_row, new_film, owner_sql, routes,  # noqa: F401
                           set_clock, sign_in)
from tests.dbkit import BACKEND_DIR
from tests.xct._support import rg

NOW = datetime(2026, 10, 18, 9, 30, 0, 123000, tzinfo=timezone.utc)  # the FakeClock's instant
WINDOW = "display_from = '2026-10-01T00:00:00Z', display_until = '2026-10-30T00:00:00Z'"


def _complete(client, **sets) -> dict:
    film = new_film(client)
    owner_sql(client.db, f"UPDATE movie SET poster_object_key = 'posters/1/{'a' * 32}', {WINDOW} WHERE id = %s", (film["id"],))
    for column, value in sets.items():
        owner_sql(client.db, f"UPDATE movie SET {column} = %s WHERE id = %s", (value, film["id"]))
    return film


def test_the_predicate_lives_in_one_function_and_every_caller_imports_it():
    hits = rg(r"published_at IS NOT NULL|published_at[.]isnot", "backend/app")
    assert [h[0] for h in hits] == ["backend/app/domain/visibility.py"]
    callers = []
    for path in (BACKEND_DIR / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "app.domain.visibility"
                    for a in n.names}
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        if "visible" in used and path.name != "visibility.py":
            callers.append(path.name)
            assert "visible" in imported and "visible" not in defined, path
    assert sorted(callers) == ["catalogue.py", "films.py"]


def test_publish_stamps_the_clock_instant_increments_once_and_audits(client):
    admin = sign_in(client)
    film = _complete(client)
    r = client.post(f"/api/admin/movies/{film['id']}/publish", json={"version": 1})
    assert r.status_code == 200, r.text
    assert (r.json()["published_at"], r.json()["version"], r.json()["published"]) == ("2026-10-18T09:30:00Z", 2, True)
    listed = [i for i in client.get("/api/admin/movies").json()["items"] if i["id"] == film["id"]][0]
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$", listed["published_at"])
    assert owner_sql(client.db, "SELECT published_at FROM movie WHERE id = %s", (film["id"],)) == [(NOW,)]
    assert owner_sql(client.db, "SELECT before, after, actor_user_id FROM audit_log WHERE action = 'movie.published' "
                                "AND entity_id = %s", (film["id"],)) == [
        ({"published_at": None}, {"published_at": "2026-10-18T09:30:00.123000Z"}, admin)]


def test_each_blocked_publish_is_409_with_its_sentence_and_the_row_unchanged(client):
    sign_in(client)
    cases = [({"poster_object_key": None}, "PUBLISH_BLOCKED", "This film has no poster. Upload a poster before publishing it."),
             ({"display_until": None}, "PUBLISH_BLOCKED",
              "This film has no display window. Set the dates it is shown between before publishing it."),
             ({"display_from": None}, "PUBLISH_BLOCKED",
              "This film has no display window. Set the dates it is shown between before publishing it."),
             ({"published_at": "2026-10-02T00:00:00Z"}, "PUBLISH_BLOCKED", "This film is already published.")]
    for sets, code, message in cases:
        film = _complete(client, **sets)
        row, audits = movie_row(client.db, film["id"]), count(client.db, "audit_log")
        r = client.post(f"/api/admin/movies/{film['id']}/publish", json={"version": 1})
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, code, message), sets
        assert movie_row(client.db, film["id"]) == row and count(client.db, "audit_log") == audits
    film = _complete(client)
    r = client.post(f"/api/admin/movies/{film['id']}/publish", json={"version": 5})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    r = client.post(f"/api/admin/movies/{film['id']}/publish", json={"version": 1, "published_at": "2026-01-01T00:00:00Z"})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "REQUEST_INVALID")
    r = client.post(f"/api/admin/movies/{film['id']}/publish", json={})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED")


def test_both_preconditions_are_read_inside_the_transaction(client):
    sign_in(client)
    film = _complete(client)
    engine = client.app.state.db_engine.sync_engine
    fired = []

    def clear_window_first(conn, cursor, statement, *args):
        # The handler has begun (its transaction is open) and is about to take the row lock; a second connection
        # clears the window now, before the write. A precondition read from anywhere but that lock would miss it.
        if "FOR UPDATE" in statement and "FROM movie" in statement and not fired:
            fired.append(owner_sql(client.db, "UPDATE movie SET display_until = NULL WHERE id = %s", (film["id"],)))

    event.listen(engine, "before_cursor_execute", clear_window_first)
    try:
        r = client.post(f"/api/admin/movies/{film['id']}/publish", json={"version": 1})
    finally:
        event.remove(engine, "before_cursor_execute", clear_window_first)
    assert fired
    assert (r.status_code, r.json()["error"]["code"]) == (409, "PUBLISH_BLOCKED")
    assert owner_sql(client.db, "SELECT published_at FROM movie WHERE id = %s", (film["id"],)) == [(None,)]


def test_published_but_before_its_window_is_invisible_to_a_guest_and_a_customer(client):
    sign_in(client)
    make_screen(client.db, make_cinema(client.db))
    film = _complete(client, display_from="2026-10-25T00:00:00Z")
    assert client.post(f"/api/admin/movies/{film['id']}/publish", json={"version": 1}).json()["window_open"] is False
    for who in ("guest", "customer"):
        client.cookies.clear()
        if who == "customer":
            sign_in(client, "customer")
        assert film["id"] not in [m["id"] for m in client.get("/api/movies").json()["movies"]], who
        assert client.get(f"/api/movies/{film['id']}").status_code == 404, who
    set_clock(client.clock, "2026-10-25T00:00:00+00:00")  # the window opens: the same film is now listed
    assert film["id"] in [m["id"] for m in client.get("/api/movies").json()["movies"]]


def test_the_editor_response_carries_two_separate_gates_and_no_combined_flag(client):
    declared = set(Film.model_fields)
    assert {"published", "window_open"} <= declared
    assert declared.isdisjoint({"live", "is_live", "visible"})
    for route in routes(client.app):
        if route.path.startswith("/api/admin/movies/") and route.response_model is not None:
            assert route.response_model is Film, route.path

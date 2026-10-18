"""S-ADM-09 - a showtime is created by hand, and nothing else creates one (P-ADM-07).

NOT covered: "a showtime already carrying a withdrawn format_id still returns it on a GET" needs the
browse GET (Phase 3); the ripgrep "INSERT INTO showtime|Showtime[(] hits exactly three files" needs
scripts/seed.py and names backend/app/domain/showtimes.py (see the lane report); the runtime PATCH needs
EP-ADM-04 (Phase 6) and is proved here against a direct runtime change instead.
"""

from __future__ import annotations

import threading
import time

import psycopg

from tests.adm.kit import (audit_rows, client, count, make_movie, make_screen, make_seats, one, sign_in)  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import rg


def _hall(db, active=True):
    hall = make_screen(db, active=active)
    make_seats(db, hall, 5)
    return hall


def _body(movie, hall, **over):
    return {"movie_id": movie, "screen_id": hall, "starts_at": "2026-09-04 18:30", "ends_at": "2026-09-04 20:58",
            "base_price_paise": 25000, **over}


def test_create_converts_naive_local_to_utc_and_returns_naive_local(client):
    admin = sign_in(client)
    hall, movie = _hall(client.db), make_movie(client.db, runtime=148)
    r = client.post("/api/admin/showtimes", json=_body(movie, hall))
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["starts_at"], body["ends_at"], body["version"]) == ("2026-09-04T18:30:00", "2026-09-04T20:58:00", 1)
    stored = owner_sql(client.db, "SELECT to_char(starts_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS'), "
                                  "to_char(ends_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') FROM showtime WHERE id = %s",
                       (body["id"],))
    assert stored == [("2026-09-04T13:00:00", "2026-09-04T15:28:00")]
    rows = audit_rows(client.db, "entity_type = 'showtime' AND entity_id = %s", (body["id"],))
    assert [(r[0], r[3], r[5]) for r in rows] == [("showtime.created", None, admin)]


def test_a_z_an_offset_or_a_zone_name_is_422_and_never_coerced(client):
    sign_in(client)
    hall, movie = _hall(client.db), make_movie(client.db)
    before = count(client.db, "showtime")
    for value in ("2026-09-04T18:30:00Z", "2026-09-04T18:30:00+05:30", "2026-09-04T18:30:00 Asia/Kolkata",
                  "2026-09-04T18:30:00[Asia/Kolkata]"):
        for field in ("starts_at", "ends_at"):
            r = client.post("/api/admin/showtimes", json=_body(movie, hall, **{field: value}))
            assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), (field, value)
    assert count(client.db, "showtime") == before


def test_a_draft_film_is_accepted_and_a_past_start_is_accepted(client):
    sign_in(client)
    hall, movie = _hall(client.db), make_movie(client.db)
    assert owner_sql(client.db, "SELECT published_at FROM movie WHERE id = %s", (movie,)) == [(None,)]
    assert client.post("/api/admin/showtimes", json=_body(movie, hall)).status_code == 201
    r = client.post("/api/admin/showtimes", json=_body(movie, hall, starts_at="2020-01-01 10:00", ends_at="2020-01-01 12:00"))
    assert r.status_code == 201  # the injected clock reads 2026-10-18; the seed needs history


def test_refusals_for_the_hall_the_film_and_the_interval(client):
    sign_in(client)
    movie = make_movie(client.db)
    r = client.post("/api/admin/showtimes", json=_body(movie, _hall(client.db, active=False)))
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
        409, "LAYOUT_FROZEN", "This hall is out of service. Bring it back into service before creating showtimes on it.")
    empty = make_screen(client.db)
    r = client.post("/api/admin/showtimes", json=_body(movie, empty))
    assert (r.status_code, r.json()["error"]["code"]) == (409, "LAYOUT_FROZEN")
    hall = _hall(client.db)
    assert client.post("/api/admin/showtimes", json=_body(987654321, hall)).status_code == 404
    assert client.post("/api/admin/showtimes", json=_body(movie, 987654321)).status_code == 404
    for ends in ("2026-09-04 18:30", "2026-09-04 18:29"):
        r = client.post("/api/admin/showtimes", json=_body(movie, hall, ends_at=ends))
        assert (r.status_code, r.json()["error"]["message"]) == (422, "The showtime must end after it starts.")


def test_a_withdrawn_format_is_refused_on_create(client):
    sign_in(client)
    hall, movie = _hall(client.db), make_movie(client.db)
    fmt = one(client.db, "INSERT INTO format (name, is_active) VALUES ('Withdrawn fmt', false) RETURNING id")
    assert client.post("/api/admin/showtimes", json=_body(movie, hall, format_id=fmt)).status_code == 422
    live = one(client.db, "INSERT INTO format (name, is_active) VALUES ('Live fmt', true) RETURNING id")
    r = client.post("/api/admin/showtimes", json=_body(movie, hall, format_id=live))
    assert r.status_code == 201 and r.json()["format_id"] == live


def test_the_display_window_bounds_starts_at_and_a_null_window_accepts_anything(client):
    sign_in(client)
    hall = _hall(client.db)
    windowed = make_movie(client.db, window=("2026-09-01T00:00:00+05:30", "2026-09-08T00:00:00+05:30"))
    counts = lambda: (count(client.db, "showtime"), count(client.db, "showtime_seat"), count(client.db, "audit_log"))  # noqa: E731
    before = counts()
    for starts in ("2026-08-31 23:59", "2026-09-08 00:00"):
        r = client.post("/api/admin/showtimes", json=_body(windowed, hall, starts_at=starts, ends_at="2026-09-09 03:00"))
        assert (r.status_code, r.json()["error"]["message"]) == (422, "This film's display window does not cover that start "
                                                                      "time. Change the time, or widen the film's window first.")
    assert counts() == before
    assert client.post("/api/admin/showtimes", json=_body(windowed, hall, starts_at="2026-09-01 00:00",
                                                          ends_at="2026-09-01 02:00")).status_code == 201
    draft = make_movie(client.db)
    assert client.post("/api/admin/showtimes", json=_body(draft, hall, starts_at="2031-01-01 10:00",
                                                          ends_at="2031-01-01 12:00")).status_code == 201


def test_the_insert_waits_on_the_screen_row_lock(client):
    sign_in(client)
    hall, movie = _hall(client.db), make_movie(client.db)
    result = {}
    with psycopg.connect(client.db.owner_url) as holder:
        # FOR SHARE, not FOR UPDATE: it blocks only a writer that takes FOR UPDATE on the screen row, and lets
        # the FOR KEY SHARE that a foreign-key check takes pass - so a wait proves the explicit lock, not the FK.
        holder.execute("SELECT id FROM screen WHERE id = %s FOR SHARE", (hall,))
        thread = threading.Thread(target=lambda: result.setdefault("r", client.post("/api/admin/showtimes",
                                                                                     json=_body(movie, hall))))
        thread.start()
        waiting = []
        for _ in range(100):
            waiting = owner_sql(client.db, "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE NOT "
                                           "l.granted AND a.usename = 'frontrow_app' AND a.datname = current_database()")
            if waiting:
                break
            time.sleep(0.05)
        assert owner_sql(client.db, "SELECT count(*) FROM pg_locks WHERE granted = false AND pid = %s", (waiting[0][0],)) == [(1,)]
        assert "r" not in result
        holder.rollback()
    thread.join(timeout=10)
    assert result["r"].status_code == 201


def test_nothing_schedules_and_no_worker_or_job_creates_a_showtime():
    assert rg(r"INSERT INTO showtime|Showtime[(]|insert[(]showtime[)]", "backend/app/workers", "backend/app/jobs") == []
    assert {h[0] for h in rg(r"insert[(]showtime[)]", "backend/app")} == {"backend/app/domain/admin/showtimes.py"}
    assert rg(r"APScheduler|celery|crontab|cron.d|schedule[.]every|EventBridge", "backend/app", "backend/migrations",
              "frontend/src", "scripts", ".github/workflows") == []


def test_ends_at_is_stored_never_derived_from_runtime(client):
    sign_in(client)
    hall, movie = _hall(client.db), make_movie(client.db, runtime=148)
    st = client.post("/api/admin/showtimes", json=_body(movie, hall, starts_at="2026-09-10 18:30",
                                                         ends_at="2026-09-10 20:58")).json()["id"]
    before = owner_sql(client.db, "SELECT ends_at::text FROM showtime WHERE id = %s", (st,))
    owner_sql(client.db, "UPDATE movie SET runtime_minutes = 120 WHERE id = %s", (movie,))
    assert owner_sql(client.db, "SELECT ends_at::text FROM showtime WHERE id = %s", (st,)) == before

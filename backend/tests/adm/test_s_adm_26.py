"""S-ADM-26 - a film's display window in naive local time (P-ADM-04, E6 S4 'naive local in both directions')."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.adm.kit import (client, count, make_cinema, make_screen, movie_row, new_film, owner_sql, set_clock,  # noqa: F401
                           sign_in)


@pytest.fixture
def film(client):
    sign_in(client)
    if count(client.db, "cinema") == 0:
        make_screen(client.db, make_cinema(client.db, timezone="Asia/Kolkata"))
    return new_film(client)


def _window(db, movie_id: int) -> tuple:
    return owner_sql(db, "SELECT display_from, display_until FROM movie WHERE id = %s", (movie_id,))[0]


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_a_zone_designator_in_either_field_is_422_and_never_coerced(client, film):
    for value in ("2026-09-04T00:00:00Z", "2026-09-04T00:00:00+05:30", "2026-09-04T00:00:00 Asia/Kolkata"):
        for key in ("display_from", "display_until"):
            r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, key: value})
            assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), (key, value)
    assert _window(client.db, film["id"]) == (None, None)


def test_local_values_are_stored_as_the_instant_less_five_thirty_and_returned_naive(client, film):
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2026-09-04 00:00",
                                                                "display_until": "2026-10-02 00:00"})
    assert r.status_code == 200, r.text
    assert _window(client.db, film["id"]) == (_utc("2026-09-03T18:30:00Z"), _utc("2026-10-01T18:30:00Z"))
    got = client.get(f"/api/admin/movies/{film['id']}").json()
    assert (got["display_from"], got["display_until"]) == ("2026-09-04T00:00:00", "2026-10-02T00:00:00")


def test_display_until_is_exclusive_against_the_injected_clock(client, film):
    client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2026-09-04 00:00",
                                                           "display_until": "2026-10-02 00:00"})
    owner_sql(client.db, "UPDATE movie SET published_at = '2026-09-01T00:00:00Z' WHERE id = %s", (film["id"],))
    client.cookies.clear()
    set_clock(client.clock, "2026-10-01T18:29:59+00:00")
    assert film["id"] in [m["id"] for m in client.get("/api/movies").json()["movies"]]
    set_clock(client.clock, "2026-10-01T18:30:00+00:00")
    assert film["id"] not in [m["id"] for m in client.get("/api/movies").json()["movies"]]


def test_nothing_is_rounded_or_derived_and_one_half_alone_leaves_the_other(client, film):
    client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2026-09-04 00:00",
                                                           "display_until": "2026-10-02 00:00"})
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 2, "display_from": "2026-09-04 09:15"})
    assert r.status_code == 200
    assert _window(client.db, film["id"]) == (_utc("2026-09-04T03:45:00Z"), _utc("2026-10-01T18:30:00Z"))


def test_an_empty_or_inverted_window_is_422_with_nothing_written(client, film):
    client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2026-09-01 00:00",
                                                           "display_until": "2026-09-30 00:00"})
    row, audits = movie_row(client.db, film["id"]), count(client.db, "audit_log")
    for body in ({"display_from": "2026-09-10 10:00", "display_until": "2026-09-10 10:00"},
                 {"display_from": "2026-09-10 10:00", "display_until": "2026-09-10 09:59"},
                 # The merged row: one half alone is checked against the stored other half.
                 {"display_from": "2026-10-15 00:00"}, {"display_until": "2026-08-15 00:00"}):
        r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 2, **body})
        assert (r.status_code, r.json()["error"]["message"]) == (422, "The display window must end after it starts."), body
    assert movie_row(client.db, film["id"]) == row and count(client.db, "audit_log") == audits


def test_a_window_entirely_in_the_past_is_accepted(client, film):
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2025-01-01 00:00",
                                                                "display_until": "2025-02-01 00:00"})
    assert (r.status_code, r.json()["window_open"]) == (200, False)


def test_the_window_audit_row_carries_exactly_its_two_keys_and_a_title_change_writes_a_second_row(client, film):
    mark = owner_sql(client.db, "SELECT coalesce(max(id), 0) FROM audit_log")[0][0]
    client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2026-09-04 00:00",
                                                           "display_until": "2026-10-02 00:00"})
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 2, "display_until": "2026-10-05 00:00",
                                                                "title": "DEMO MOVIE 26"})
    assert r.status_code == 200
    rows = owner_sql(client.db, "SELECT action, before, after FROM audit_log WHERE entity_type = 'movie' AND entity_id = %s "
                                "AND id > %s ORDER BY id", (film["id"], mark))
    assert rows == [
        ("movie.display_window_changed", {"display_from": None, "display_until": None},
         {"display_from": "2026-09-03T18:30:00Z", "display_until": "2026-10-01T18:30:00Z"}),
        ("movie.updated", {"title": film["title"]}, {"title": "DEMO MOVIE 26"}),
        ("movie.display_window_changed", {"display_from": "2026-09-03T18:30:00Z", "display_until": "2026-10-01T18:30:00Z"},
         {"display_from": "2026-09-03T18:30:00Z", "display_until": "2026-10-04T18:30:00Z"})]


def test_a_window_change_on_a_published_film_keeps_published_at(client, film):
    owner_sql(client.db, "UPDATE movie SET published_at = '2026-10-02T04:05:06Z' WHERE id = %s", (film["id"],))
    r = client.patch(f"/api/admin/movies/{film['id']}", json={"version": 1, "display_from": "2026-10-01 00:00",
                                                                "display_until": "2026-11-01 00:00"})
    assert (r.status_code, r.json()["published_at"]) == (200, "2026-10-02T04:05:06Z")
    assert owner_sql(client.db, "SELECT published_at FROM movie WHERE id = %s", (film["id"],)) == [(_utc("2026-10-02T04:05:06Z"),)]

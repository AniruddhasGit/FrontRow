"""S-ADM-28 - withdraw a film without deleting anything (P-ADM-06, EP-ADM-08).

NOT covered, and why: the AC asks that GET /api/me/bookings/{reference} and the receipt still return the film's
"poster reference and runtime_minutes". Neither surface carries either field (EP-ACC-08 and EP-TKT-01, owned by the
account and ticket lanes); the real TITLE is asserted on both. "The SES test double records zero calls" is asserted as
nothing queued for sending (outbox_message and receipt_dispatch unchanged): the api process never calls SES itself.
"""

from __future__ import annotations

from tests.adm.kit import (cached_client, client, count, make_category, make_cinema, make_screen, make_seat,  # noqa: F401
                           make_showtime, movie_row, new_film, owner_sql, routes, sign_in)
from tests.brw.kit import book_seat

PUBLISHED = ("UPDATE movie SET published_at = '2026-10-02T04:05:06Z', poster_object_key = 'posters/1/{}', "
             "display_from = '2026-10-01T00:00:00Z', display_until = '2026-10-30T00:00:00Z' WHERE id = %s").format("a" * 32)


def _published(client) -> dict:
    film = new_film(client)
    owner_sql(client.db, PUBLISHED, (film["id"],))
    return film


def test_unpublish_nulls_published_at_increments_once_and_audits_the_prior_instant(client):
    admin = sign_in(client)
    film = _published(client)
    r = client.post(f"/api/admin/movies/{film['id']}/unpublish", json={"version": 1})
    assert (r.status_code, r.json()["published_at"], r.json()["version"], r.json()["published"]) == (200, None, 2, False)
    assert owner_sql(client.db, "SELECT before, after, actor_user_id FROM audit_log WHERE action = 'movie.unpublished' "
                                "AND entity_id = %s", (film["id"],)) == [
        ({"published_at": "2026-10-02T04:05:06Z"}, {"published_at": None}, admin)]


def test_a_draft_is_409_with_its_sentence_and_a_stale_version_changes_nothing(client):
    sign_in(client)
    draft = new_film(client)
    r = client.post(f"/api/admin/movies/{draft['id']}/unpublish", json={"version": 1})
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
        409, "PUBLISH_BLOCKED", "This film is not published, so there is nothing to withdraw.")
    film = _published(client)
    row, audits = movie_row(client.db, film["id"]), count(client.db, "audit_log")
    r = client.post(f"/api/admin/movies/{film['id']}/unpublish", json={"version": 3})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    assert movie_row(client.db, film["id"]) == row and count(client.db, "audit_log") == audits


def test_showtimes_and_bookings_survive_and_the_first_listing_after_the_200_drops_the_film(cached_client):
    c = cached_client
    sign_in(c)
    hall = make_screen(c.db, make_cinema(c.db))
    category = make_category(c.db)
    seats = [make_seat(c.db, hall, f"B{n}", category) for n in (1, 2)]
    film = _published(c)
    future = make_showtime(c.db, hall, film["id"], "2026-10-25T13:00:00Z", "2026-10-25T15:30:00Z")
    bookings = [book_seat(c.db, future, s) for s in seats]
    customer = owner_sql(c.db, "SELECT user_id FROM booking WHERE id = %s", (bookings[0],))[0][0]
    reference = owner_sql(c.db, "SELECT reference FROM booking WHERE id = %s", (bookings[0],))[0][0]
    state = "SELECT status, cancelled_at, total_paise FROM booking WHERE id = ANY(%s) ORDER BY id"
    before = (count(c.db, "showtime", "movie_id = %s", (film["id"],)),
              count(c.db, "booking JOIN showtime ON showtime.id = booking.showtime_id", "showtime.movie_id = %s", (film["id"],)),
              owner_sql(c.db, state, (bookings,)), count(c.db, "outbox_message"), count(c.db, "receipt_dispatch"))
    assert film["id"] in [m["id"] for m in c.get("/api/movies").json()["movies"]]  # primes the 60 s listing cache
    r = c.post(f"/api/admin/movies/{film['id']}/unpublish", json={"version": 1})
    assert r.status_code == 200
    assert film["id"] not in [m["id"] for m in c.get("/api/movies").json()["movies"]]  # no sleep, no TTL elapsed
    after = (count(c.db, "showtime", "movie_id = %s", (film["id"],)),
             count(c.db, "booking JOIN showtime ON showtime.id = booking.showtime_id", "showtime.movie_id = %s", (film["id"],)),
             owner_sql(c.db, state, (bookings,)), count(c.db, "outbox_message"), count(c.db, "receipt_dispatch"))
    assert after == before and before[2] == [("confirmed", None, 25000)] * 2
    # The customer's own reads go to the movie row directly, not through the visibility predicate.
    from app.core.security import SESSION_COOKIE, issue_session_token
    from tests.dbkit import app_settings

    c.cookies.set(SESSION_COOKIE, issue_session_token(user_id=customer, role="customer", password_version=1,
                                                      now=c.clock.now(), settings=app_settings(c.db)))
    mine = c.get(f"/api/me/bookings/{reference}")
    assert mine.status_code == 200, mine.text
    assert mine.json()["movie_title"] == film["title"]
    receipt = c.get(f"/api/bookings/by-reference/{reference}")
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["film_title"] == film["title"]


def test_there_is_no_delete_on_a_film_and_the_request_changes_nothing(client):
    sign_in(client)
    film = new_film(client)
    movies = count(client.db, "movie")
    r = client.delete(f"/api/admin/movies/{film['id']}")
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
        405, "METHOD_NOT_ALLOWED", "That action is not available. Nothing was changed.")
    assert count(client.db, "movie") == movies
    assert [r.path for r in routes(client.app) if "DELETE" in r.methods and r.path.startswith("/api/admin/movies")] == []

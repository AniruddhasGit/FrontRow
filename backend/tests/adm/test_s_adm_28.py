"""S-ADM-28 - withdraw a film without deleting anything (P-ADM-06, EP-ADM-08).

The customer's surfaces are GET /api/me/bookings/{reference}, GET /api/bookings/by-reference/{reference} (EP-TKT-01) and
the emailed receipt, whose facts the worker reads at send time (app/workers Worker._facts, rendered by
app/workers/render.receipt). The title on all three is compared before and after the withdrawal, and a statement
listener on each engine finds no published_at condition. "The SES test double records zero calls": every mail
transport's send is replaced by a recorder for the unpublish request, and nothing is queued (outbox_message and
receipt_dispatch unchanged), so no later worker run sends anything either.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import event

from app.core.security import SESSION_COOKIE, issue_session_token
from app.domain import mail
from app.workers import render
from tests.adm.kit import (cached_client, client, count, make_category, make_cinema, make_screen, make_seat,  # noqa: F401
                           make_showtime, movie_row, new_film, owner_sql, routes, sign_in)
from tests.brw.kit import book_seat
from tests.dbkit import app_settings
from tests.tkt import kit as tkt

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


def test_showtimes_and_bookings_survive_and_the_first_listing_after_the_200_drops_the_film(cached_client, monkeypatch):
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
    admin_cookie = c.cookies.get(SESSION_COOKIE)
    titles_before = _customer_titles(c, customer, reference, bookings[0])
    c.cookies.set(SESSION_COOKIE, admin_cookie)
    assert film["id"] in [m["id"] for m in c.get("/api/movies").json()["movies"]]  # primes the 60 s listing cache
    sends: list[str] = []
    with monkeypatch.context() as m:  # the SES test double: every mail transport's send, recorded
        for transport in (mail.SesTransport, mail.StubTransport, mail.ResendTransport):
            m.setattr(transport, "send", lambda self, to, msg, _t=transport.__name__: sends.append(_t))
        r = c.post(f"/api/admin/movies/{film['id']}/unpublish", json={"version": 1})
        assert r.status_code == 200
        assert film["id"] not in [m_["id"] for m_ in c.get("/api/movies").json()["movies"]]  # no sleep, no TTL elapsed
    assert sends == []
    after = (count(c.db, "showtime", "movie_id = %s", (film["id"],)),
             count(c.db, "booking JOIN showtime ON showtime.id = booking.showtime_id", "showtime.movie_id = %s", (film["id"],)),
             owner_sql(c.db, state, (bookings,)), count(c.db, "outbox_message"), count(c.db, "receipt_dispatch"))
    assert after == before and before[2] == [("confirmed", None, 25000)] * 2
    # The customer's own reads and the receipt go to the movie row directly, not through the visibility predicate:
    # the same title, byte for byte, and no statement behind any of them carries a published_at condition.
    titles_after = _customer_titles(c, customer, reference, bookings[0])
    assert titles_after == titles_before == (film["title"],) * 3


def _customer_titles(c, customer: int, reference: str, booking_id: int) -> tuple:
    """GET /api/me/bookings/{reference}, GET /api/bookings/by-reference/{reference} and the worker's receipt, each with a
    statement listener asserting that no statement it issues names published_at."""
    statements: list[str] = []
    capture = lambda conn, cur, statement, *rest: statements.append(statement)  # noqa: E731
    event.listen(c.app.state.db_engine.sync_engine, "before_cursor_execute", capture)
    try:
        c.cookies.set(SESSION_COOKIE, issue_session_token(user_id=customer, role="customer", password_version=1,
                                                          now=c.clock.now(), settings=app_settings(c.db)))
        mine = c.get(f"/api/me/bookings/{reference}")
        receipt = c.get(f"/api/bookings/by-reference/{reference}")
    finally:
        event.remove(c.app.state.db_engine.sync_engine, "before_cursor_execute", capture)
    assert mine.status_code == 200 and receipt.status_code == 200, (mine.text, receipt.text)
    assert any("FROM movie" in s or "JOIN movie" in s for s in statements), statements
    assert not [s for s in statements if "published_at" in s]

    async def mailed() -> tuple[str, list[str]]:
        w = tkt.worker(c.db, c.clock)
        seen: list[str] = []
        event.listen(w.engine.sync_engine, "before_cursor_execute", lambda conn, cur, s, *rest: seen.append(s))
        try:
            facts, to = await w._facts(booking_id)
            assert facts.film in render.receipt(facts, to, w.settings).get_body(("plain",)).get_content()
            return facts.film, seen
        finally:
            await w.engine.dispose()

    mailed_title, worker_statements = asyncio.run(mailed())
    assert any("JOIN movie" in s for s in worker_statements) and not [s for s in worker_statements if "published_at" in s]
    return mine.json()["movie_title"], receipt.json()["film_title"], mailed_title


def test_there_is_no_delete_on_a_film_and_the_request_changes_nothing(client):
    sign_in(client)
    film = new_film(client)
    movies = count(client.db, "movie")
    r = client.delete(f"/api/admin/movies/{film['id']}")
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
        405, "METHOD_NOT_ALLOWED", "That action is not available. Nothing was changed.")
    assert count(client.db, "movie") == movies
    assert [r.path for r in routes(client.app) if "DELETE" in r.methods and r.path.startswith("/api/admin/movies")] == []

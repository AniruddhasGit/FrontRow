"""CR-008 T9 search, T11/T12 film details, ratings and likes - the rating gate is the server's, tested with a refusal.

The pay lane's world (tests/pay/kit.py): one film "The Long Night", showtime 7 at 20:00 IST on 14 Aug (14:30Z); the
clock starts at 14:00Z, half an hour before it.
"""

from __future__ import annotations

import pytest

from tests.brw.kit import make_lookup, make_movie
from tests.pay.kit import C1, C2, F7, SHOWTIME, api, book, clock_at, cookies, count, owner_sql, user, world7

pytestmark = pytest.mark.anyio
AFTER_START = "2026-08-14T15:00:00+00:00"


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_every_new_account_route_needs_a_session(world):
    film = world["movie"]
    async with api(world["db"], clock_at()) as c:
        for method, path in [("GET", f"/api/me/movies/{film}"), ("PUT", f"/api/me/ratings/{film}"), ("PUT", f"/api/me/likes/{film}")]:
            r = await c.request(method, path, json={})
            assert (r.status_code, r.json()["error"]["code"]) == (401, "AUTH_REQUIRED"), path


async def test_rating_is_refused_without_a_started_paid_booking_and_counted_after(world):
    db, film = world["db"], world["movie"]
    viewer, stranger = user(db), user(db)
    book(db, viewer, SHOWTIME, [F7])
    clock = clock_at()  # 14:00Z: the show has not started yet
    async with api(db, clock) as c:
        mine, theirs = cookies(c, viewer), cookies(c, stranger)
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 8}, cookies=mine)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")  # booked, but the show has not started
        assert (await c.get(f"/api/me/movies/{film}", cookies=mine)).json()["can_rate"] is False
        clock.set(AFTER_START)
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 8}, cookies=theirs)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")  # never booked: refused
        assert (await c.get(f"/api/me/movies/{film}", cookies=mine)).json() == {
            "movie_id": film, "score": None, "can_rate": True, "liked": False, "coming_soon": False,
            "review": None, "review_id": None, "voted": []}  # review, review_id, voted: CR-011 F4
        for bad, status in (({"score": 0}, 422), ({"score": 11}, 422), ({"score": "8"}, 400), ({"score": 8, "x": 1}, 400)):
            assert (await c.put(f"/api/me/ratings/{film}", json=bad, cookies=mine)).status_code == status, bad
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 8}, cookies=mine)
        assert r.status_code == 200, r.text
        assert r.json()["rating"] == {"average_tenths": 80, "count": 1, "breakdown": [0, 0, 0, 0, 0, 0, 0, 1, 0, 0]}
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 7}, cookies=mine)  # re-rating updates the one row
        assert r.json()["rating"]["count"] == 1 and r.json()["score"] == 7
        listed = (await c.get("/api/movies")).json()["movies"][0]
        assert listed["rating"] == {"average_tenths": 70, "count": 1} and listed["likes"] == 0
        detail = (await c.get(f"/api/movies/{film}")).json()
        assert detail["rating"]["breakdown"][6] == 1 and (await c.get(f"/api/me/movies/{film}", cookies=mine)).json()["score"] == 7
    assert count(db, "SELECT count(*) FROM movie_rating") == 1


async def test_the_average_is_half_up_in_tenths_and_a_failed_payment_is_no_ticket(world):
    db, film = world["db"], world["movie"]
    a, b, unpaid = user(db), user(db), user(db)
    book(db, a, SHOWTIME, [C1])
    book(db, b, SHOWTIME, [C2])
    bid, _ = book(db, unpaid, SHOWTIME, [F7])
    owner_sql(db, "UPDATE payment SET state = 'failed' WHERE id = (SELECT payment_id FROM booking WHERE id = %s)", (bid,))
    async with api(db, clock_at(AFTER_START)) as c:
        await c.put(f"/api/me/ratings/{film}", json={"score": 7}, cookies=cookies(c, a))
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 8}, cookies=cookies(c, b))
        assert r.json()["rating"]["average_tenths"] == 75  # 7.5, not 7 or 8 (the half-up rule is exercised)
        assert (await c.put(f"/api/me/ratings/{film}", json={"score": 1}, cookies=cookies(c, unpaid))).status_code == 403


async def test_likes_are_for_films_not_yet_out_toggle_and_count(world):
    db, film = world["db"], world["movie"]
    soon = make_movie(db, title="Tomorrow's Film")
    owner_sql(db, "UPDATE movie SET release_date = '2026-08-30' WHERE id = %s", (soon,))
    owner_sql(db, "UPDATE movie SET release_date = '2026-08-14' WHERE id = %s", (film,))  # out today (IST)
    me, other = user(db), user(db)
    async with api(db, clock_at()) as c:
        mine = cookies(c, me)
        r = await c.put(f"/api/me/likes/{film}", json={"liked": True}, cookies=mine)
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")
        for _ in range(2):
            r = await c.put(f"/api/me/likes/{soon}", json={"liked": True}, cookies=mine)
            assert r.json() == {"movie_id": soon, "liked": True, "likes": 1}
        assert (await c.put(f"/api/me/likes/{soon}", json={"liked": True}, cookies=cookies(c, other))).json()["likes"] == 2
        assert (await c.put(f"/api/me/likes/{soon}", json={"liked": False}, cookies=mine)).json()["likes"] == 1
        films = {m["id"]: m for m in (await c.get("/api/movies")).json()["movies"]}
        assert (films[soon]["coming_soon"], films[soon]["release_date"], films[soon]["likes"]) == (True, "2026-08-30", 1)
        assert films[film]["coming_soon"] is False
        assert (await c.put(f"/api/me/ratings/{soon}", json={"score": 9}, cookies=mine)).status_code == 403
    assert count(db, "SELECT count(*) FROM movie_like") == 2


async def test_search_finds_titles_and_genres_of_visible_films_only(world):
    db, film = world["db"], world["movie"]
    thriller = make_lookup(db, "genre", "Thriller")
    owner_sql(db, "INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s)", (film, thriller))
    other = make_movie(db, title="Night Thriller Club")
    hidden = make_movie(db, title="Night Draft", published_at=None)
    async with api(db, clock_at()) as c:
        r = (await c.get("/api/search", params={"q": "  NIGHT "})).json()["items"]
        assert [i["id"] for i in r] == [other, film] and hidden not in [i["id"] for i in r]
        r = (await c.get("/api/search", params={"q": "thrill"})).json()["items"]
        assert {(i["id"], i["matched"]) for i in r} == {(other, "title"), (film, "genre")}
        assert r[0]["genres"] == [] and r[1]["genres"] == [{"id": thriller, "name": "Thriller"}]
        assert (await c.get("/api/search", params={"q": "n"})).json() == {"items": []}
        assert (await c.get("/api/search", params={"q": "%"})).json() == {"items": []}  # not a wildcard
        assert (await c.get("/api/search", params={"q": "x" * 101})).status_code == 422


async def test_the_film_page_carries_full_details_the_admin_edits(world):
    db, film = world["db"], world["movie"]
    owner_sql(db, "UPDATE movie SET release_date = '2026-08-01', cast_members = %s, crew_members = %s WHERE id = %s",
              ("Mira Hale: Dr. Ines Varga\nTomas Reed\n\n", "Ana Ruiz: Director", film))
    async with api(db, clock_at()) as c:
        d = (await c.get(f"/api/movies/{film}")).json()
    assert d["release_date"] == "2026-08-01" and d["coming_soon"] is False
    assert d["cast"] == [{"name": "Mira Hale", "role": "Dr. Ines Varga"}, {"name": "Tomas Reed", "role": None}]
    assert d["crew"] == [{"name": "Ana Ruiz", "role": "Director"}]
    assert d["rating"] == {"average_tenths": None, "count": 0, "breakdown": [0] * 10}

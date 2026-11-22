"""CR-011 F4: reviews (stars + text) by verified viewers only, editable by their author, listed newest / most helpful,
with one Helpful vote per customer per review and none on one's own. The gates are the server's, tested with refusals.

The pay lane's world (tests/pay/kit.py): showtime 7 of "The Long Night" starts 20:00 IST on 14 Aug (14:30Z).
"""

from __future__ import annotations

import pytest

from tests.pay.kit import C1, C2, F7, SHOWTIME, api, book, clock_at, cookies, count, owner_sql, user, world7

pytestmark = pytest.mark.anyio
AFTER_START = "2026-08-14T15:00:00+00:00"
LATER = "2026-08-14T16:00:00+00:00"


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_only_a_verified_viewer_reviews_and_the_author_edits_it(world):
    db, film = world["db"], world["movie"]
    viewer, stranger = user(db), user(db)
    book(db, viewer, SHOWTIME, [F7])
    owner_sql(db, "UPDATE users SET display_name = 'Asha' WHERE id = %s", (viewer,))
    clock = clock_at()
    async with api(db, clock) as c:
        assert (await c.put(f"/api/me/reviews/{film}", json={"score": 8, "text": "x"})).status_code == 401
        r = await c.put(f"/api/me/reviews/{film}", json={"score": 8, "text": "Great."}, cookies=cookies(c, viewer))
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")  # booked, the show has not started
        clock.set(AFTER_START)
        r = await c.put(f"/api/me/reviews/{film}", json={"score": 8, "text": "Great."}, cookies=cookies(c, stranger))
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")  # never booked
        mine = cookies(c, viewer)
        for bad, status in (({"score": 8, "text": "   "}, 422), ({"score": 8, "text": "x" * 2001}, 422),
                            ({"score": 0, "text": "ok"}, 422), ({"score": 8}, 400), ({"score": 8, "text": 5}, 400)):
            assert (await c.put(f"/api/me/reviews/{film}", json=bad, cookies=mine)).status_code == status, bad
        r = await c.put(f"/api/me/reviews/{film}", json={"score": 8, "text": "  Great sound.  "}, cookies=mine)
        assert r.status_code == 200, r.text
        assert (r.json()["text"], r.json()["rating"]["count"]) == ("Great sound.", 1)
        clock.set(LATER)
        r = await c.put(f"/api/me/reviews/{film}", json={"score": 9, "text": "Even better the second time."}, cookies=mine)
        assert r.json()["rating"]["average_tenths"] == 90  # the edit replaced the score in the same row
        listed = (await c.get(f"/api/movies/{film}/reviews")).json()
        assert listed["count"] == 1
        item = listed["items"][0]
        assert (item["author"], item["score"], item["text"], item["helpful"]) == ("Asha", 9, "Even better the second time.", 0)
        assert item["written_at"] == "2026-08-14T21:30:00+05:30"  # the edit's instant, in the cinema's offset
        assert "@" not in str(listed)  # no email anywhere
        me = (await c.get(f"/api/me/movies/{film}", cookies=mine)).json()
        assert (me["score"], me["review"], me["review_id"], me["voted"]) == (9, "Even better the second time.", item["id"], [])
        assert (await c.get(f"/api/movies/{film}/reviews", params={"sort": "best"})).status_code == 422
        assert (await c.get("/api/movies/999999/reviews")).status_code == 404
    assert count(db, "SELECT count(*) FROM movie_rating") == 1


async def test_helpful_is_once_per_customer_never_ones_own_and_sorts_the_list(world):
    db, film = world["db"], world["movie"]
    a, b, voter, rater = user(db), user(db), user(db), user(db)
    for u, seat in ((a, C1), (b, C2), (rater, F7)):
        book(db, u, SHOWTIME, [seat])
    clock = clock_at(AFTER_START)
    async with api(db, clock) as c:
        first = (await c.put(f"/api/me/reviews/{film}", json={"score": 6, "text": "Fine."}, cookies=cookies(c, a))).json()["review_id"]
        clock.set(LATER)
        second = (await c.put(f"/api/me/reviews/{film}", json={"score": 7, "text": "Good."}, cookies=cookies(c, b))).json()["review_id"]
        await c.put(f"/api/me/ratings/{film}", json={"score": 5}, cookies=cookies(c, rater))  # a score with no text
        assert (await c.post(f"/api/me/reviews/{first}/helpful")).status_code == 401
        r = await c.post(f"/api/me/reviews/{first}/helpful", cookies=cookies(c, a))
        assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN")  # the author's own review
        for _ in range(2):  # a second press changes nothing
            r = await c.post(f"/api/me/reviews/{first}/helpful", cookies=cookies(c, voter))
            assert r.json() == {"review_id": first, "helpful": 1, "voted": True}
        assert (await c.post(f"/api/me/reviews/{first}/helpful", cookies=cookies(c, b))).json()["helpful"] == 2
        rated_only = (await c.get(f"/api/me/movies/{film}", cookies=cookies(c, rater))).json()
        assert (rated_only["review"], rated_only["review_id"]) == (None, None)
        no_text = owner_sql(db, "SELECT id FROM movie_rating WHERE user_id = %s", (rater,))[0][0]
        assert (await c.post(f"/api/me/reviews/{no_text}/helpful", cookies=cookies(c, voter))).status_code == 404
        newest = (await c.get(f"/api/movies/{film}/reviews")).json()
        assert newest["count"] == 2 and [i["id"] for i in newest["items"]] == [second, first]
        assert newest["items"][1]["author"] == "FrontRow viewer"  # no display name set
        helpful = (await c.get(f"/api/movies/{film}/reviews", params={"sort": "helpful"})).json()
        assert [(i["id"], i["helpful"]) for i in helpful["items"]] == [(first, 2), (second, 0)]
        assert (await c.get(f"/api/me/movies/{film}", cookies=cookies(c, voter))).json()["voted"] == [first]
    assert count(db, "SELECT count(*) FROM review_vote") == 2

"""CR-011 F4: reviews (stars + text), editable by their author, listed newest / most helpful,
with one Helpful vote per customer per review and none on one's own. The gates are the server's, tested with refusals.

CR-013 (owner, 2026-11-23): any signed-in customer reviews a released film; each item's `verified` says whether its
author saw it here (or is a demo crowd account); a star band narrows the list.

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


async def test_a_signed_in_customer_reviews_and_the_author_edits_it(world):
    # CR-013 (owner request 2026-11-23, amended): any signed-in customer may review a released film, so the two 403s
    # this test asserted (booked but not started, never booked) are gone; the new gate is tested at the end of this file.
    db, film = world["db"], world["movie"]
    viewer = user(db)
    book(db, viewer, SHOWTIME, [F7])
    owner_sql(db, "UPDATE users SET display_name = 'Asha' WHERE id = %s", (viewer,))
    clock = clock_at()
    async with api(db, clock) as c:
        assert (await c.put(f"/api/me/reviews/{film}", json={"score": 8, "text": "x"})).status_code == 401
        clock.set(AFTER_START)
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


# ---- CR-013 (owner request 2026-11-23) -------------------------------------------------------------------------------


async def test_a_signed_in_non_viewer_rates_and_reviews_but_not_a_coming_soon_film(world):
    from tests.brw.kit import make_movie

    db, film = world["db"], world["movie"]
    soon = make_movie(db, title="Tomorrow's Film")
    owner_sql(db, "UPDATE movie SET release_date = '2026-08-30' WHERE id = %s", (soon,))
    stranger = user(db)  # never booked anything
    async with api(db, clock_at()) as c:  # before any show of the film has started
        mine = cookies(c, stranger)
        assert (await c.get(f"/api/me/movies/{film}", cookies=mine)).json()["can_rate"] is True
        r = await c.put(f"/api/me/ratings/{film}", json={"score": 6}, cookies=mine)
        assert r.status_code == 200 and r.json()["rating"]["count"] == 1, r.text
        r = await c.put(f"/api/me/reviews/{film}", json={"score": 7, "text": "Worth it."}, cookies=mine)
        assert r.status_code == 200 and r.json()["rating"]["count"] == 1, r.text  # the same one row, now with text
        listed = (await c.get(f"/api/movies/{film}/reviews")).json()["items"]
        assert [(i["score"], i["text"]) for i in listed] == [(7, "Worth it.")]
        assert (await c.get(f"/api/me/movies/{soon}", cookies=mine)).json()["can_rate"] is False
        for path, body in ((f"/api/me/ratings/{soon}", {"score": 9}), (f"/api/me/reviews/{soon}", {"score": 9, "text": "Soon!"})):
            r = await c.put(path, json=body, cookies=mine)
            assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN"), path
    assert count(db, "SELECT count(*) FROM movie_rating") == 1


async def test_verified_is_true_only_for_a_started_paid_booking_or_a_demo_crowd_account(world):
    db, film = world["db"], world["movie"]
    viewer, stranger, unpaid = user(db), user(db), user(db)
    crowd, seed = user(db, email="customer-51@example.invalid"), user(db, email="customer-01@example.invalid")
    book(db, viewer, SHOWTIME, [F7])
    bid, _ = book(db, unpaid, SHOWTIME, [C1])
    owner_sql(db, "UPDATE payment SET state = 'failed' WHERE id = (SELECT payment_id FROM booking WHERE id = %s)", (bid,))
    who = {viewer: "viewer", stranger: "stranger", unpaid: "unpaid", crowd: "crowd", seed: "seed"}
    for u, name in who.items():
        owner_sql(db, "UPDATE users SET display_name = %s WHERE id = %s", (name, u))
    clock = clock_at()  # 14:00Z: showtime 7 has not started
    async with api(db, clock) as c:
        for u in who:
            r = await c.put(f"/api/me/reviews/{film}", json={"score": 8, "text": "Good."}, cookies=cookies(c, u))
            assert r.status_code == 200, r.text

        async def badges():
            return {i["author"]: i["verified"] for i in (await c.get(f"/api/movies/{film}/reviews")).json()["items"]}

        assert await badges() == {"viewer": False, "stranger": False, "unpaid": False, "crowd": True, "seed": False}
        clock.set(AFTER_START)  # the viewer's show has started: now they saw it here
        assert await badges() == {"viewer": True, "stranger": False, "unpaid": False, "crowd": True, "seed": False}


async def test_the_star_band_narrows_the_list_combines_with_the_sort_and_counts_every_band(world):
    db, film = world["db"], world["movie"]
    ten, nine, seven, three, rated, voter = (user(db) for _ in range(6))
    clock = clock_at(AFTER_START)
    async with api(db, clock) as c:
        ids = {}
        for minute, (u, score) in enumerate(((ten, 10), (nine, 9), (seven, 7), (three, 3))):
            clock.set(f"2026-08-14T15:0{minute}:00+00:00")  # each written after the one before
            ids[score] = (await c.put(f"/api/me/reviews/{film}", json={"score": score, "text": f"A {score}."},
                                      cookies=cookies(c, u))).json()["review_id"]
        await c.put(f"/api/me/ratings/{film}", json={"score": 9}, cookies=cookies(c, rated))  # no text: in no band
        await c.post(f"/api/me/reviews/{ids[10]}/helpful", cookies=cookies(c, voter))
        everything = (await c.get(f"/api/movies/{film}/reviews")).json()
        assert everything["count"] == 4
        assert everything["bands"] == {"9-10": 2, "7-8": 1, "5-6": 0, "3-4": 1, "1-2": 0}
        top = (await c.get(f"/api/movies/{film}/reviews", params={"band": "9-10"})).json()
        assert [i["id"] for i in top["items"]] == [ids[9], ids[10]] and top["count"] == 2  # newest first
        assert top["bands"] == everything["bands"]  # every band's count, whatever the filter
        helpful = (await c.get(f"/api/movies/{film}/reviews", params={"band": "9-10", "sort": "helpful"})).json()
        assert [i["id"] for i in helpful["items"]] == [ids[10], ids[9]]  # the voted one first
        empty = (await c.get(f"/api/movies/{film}/reviews", params={"band": "5-6"})).json()
        assert (empty["count"], empty["items"]) == (0, [])
        for bad in ("9", "10-9", "0-1", "all", "9\u201310", ""):
            r = await c.get(f"/api/movies/{film}/reviews", params={"band": bad})
            assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), bad
            assert r.json()["error"]["details"] == {"field": "band"}, bad

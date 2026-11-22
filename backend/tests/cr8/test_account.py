"""CR-008 T4 bookmarks, T5 summary, T6 profile, T7 notification inbox, T8 support messages - each only on the caller's rows."""

from __future__ import annotations

import pytest

from tests.brw.kit import make_lookup, make_movie
from tests.pay.kit import F7, api, clock_at, confirm, cookies, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_every_account_route_needs_a_session(world):
    async with api(world["db"], clock_at()) as c:
        for method, path in [("GET", "/api/me/summary"), ("GET", "/api/me/rewards"), ("GET", "/api/me/bookmarks"),
                             ("PUT", f"/api/me/bookmarks/{world['movie']}"), ("GET", "/api/me/notifications"),
                             ("POST", "/api/me/notifications/read"), ("GET", "/api/me/profile"), ("PUT", "/api/me/profile")]:
            r = await c.request(method, path, json={})
            assert (r.status_code, r.json()["error"]["code"]) == (401, "AUTH_REQUIRED"), path


async def test_a_bookmark_saves_unsaves_and_is_only_the_callers(world):
    db, film = world["db"], world["movie"]
    me, other = user(db), user(db)
    hidden = make_movie(db, published_at=None)
    async with api(db, clock_at()) as c:
        mine = cookies(c, me)
        for _ in range(2):  # twice: one row, the same state
            r = await c.put(f"/api/me/bookmarks/{film}", json={"saved": True}, cookies=mine)
            assert r.status_code == 200 and r.json() == {"movie_id": film, "saved": True}
        listed = (await c.get("/api/me/bookmarks", cookies=mine)).json()["items"]
        assert [i["movie_id"] for i in listed] == [film] and listed[0]["title"] == "The Long Night"
        assert (await c.get("/api/me/bookmarks", cookies=cookies(c, other))).json()["items"] == []
        assert (await c.put(f"/api/me/bookmarks/{hidden}", json={"saved": True}, cookies=mine)).status_code == 404
        assert (await c.put(f"/api/me/bookmarks/{film}", json={"saved": "yes"}, cookies=mine)).status_code == 400
        assert (await c.put(f"/api/me/bookmarks/{film}", json={"saved": False}, cookies=mine)).status_code == 200
        assert (await c.get("/api/me/bookmarks", cookies=mine)).json()["items"] == []
    assert count(db, "SELECT count(*) FROM bookmark") == 1


async def test_the_inbox_lists_events_and_marks_read_only_the_callers(world):
    db = world["db"]
    me, other = user(db), user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, me, [F7])
        assert (await confirm(c, me, h["hold_token"])).status_code == 201
        mine = cookies(c, me)
        box = (await c.get("/api/me/notifications", cookies=mine)).json()
        assert box["unread"] == 2 and [i["kind"] for i in box["items"]] == ["points_earned", "booking_confirmed"]
        assert (await c.get("/api/me/summary", cookies=mine)).json()["unread_notifications"] == 2
        ids = [i["id"] for i in box["items"]]
        # another account naming my ids changes nothing
        assert (await c.post("/api/me/notifications/read", json={"ids": ids}, cookies=cookies(c, other))).json() == {"unread": 0}
        assert (await c.post("/api/me/notifications/read", json={"ids": ids[:1]}, cookies=mine)).json() == {"unread": 1}
        assert (await c.post("/api/me/notifications/read", json={"all": True}, cookies=mine)).json() == {"unread": 0}
        assert (await c.post("/api/me/notifications/read", json={}, cookies=mine)).status_code == 400
        assert (await c.post("/api/me/notifications/read", json={"ids": ids, "all": True}, cookies=mine)).status_code == 400
        s = (await c.get("/api/me/summary", cookies=mine)).json()
        assert s["unread_notifications"] == 0 and s["points_balance"] == 3090


async def test_the_profile_saves_validates_inline_and_reads_back(world):
    db = world["db"]
    me = user(db)
    lang, fmt = make_lookup(db, "language", "Hindi"), make_lookup(db, "format", "IMAX")
    retired = make_lookup(db, "format", "VHS", active=False)
    async with api(db, clock_at()) as c:
        mine = cookies(c, me)
        r = await c.put("/api/me/profile", cookies=mine, json={"display_name": "  Asha  ", "phone": "+91 98765-43210",
                                                                "preferred_language_id": lang, "preferred_format_id": fmt})
        assert r.status_code == 200, r.text
        got = (await c.get("/api/me/profile", cookies=mine)).json()
        assert {k: got[k] for k in ("display_name", "phone", "preferred_language_id", "preferred_format_id")} == \
            {"display_name": "Asha", "phone": "+919876543210", "preferred_language_id": lang, "preferred_format_id": fmt}
        bad = await c.put("/api/me/profile", cookies=mine, json={"display_name": "x" * 61, "phone": "12ab",
                                                                  "preferred_language_id": None, "preferred_format_id": retired})
        assert bad.status_code == 422
        assert set(bad.json()["error"]["details"]["fields"]) == {"display_name", "phone", "preferred_format_id"}
        assert (await c.put("/api/me/profile", cookies=mine, json={"display_name": "A"})).status_code == 400  # a PUT names all four
        assert (await c.get("/api/me/summary", cookies=mine)).json()["display_name"] == "Asha"  # the refusal changed nothing


async def test_a_support_message_is_stored_for_a_guest_and_for_an_account(world):
    db = world["db"]
    me = user(db, email="asha@example.invalid")
    async with api(db, clock_at()) as c:
        r = await c.post("/api/support/messages", json={"topic": "booking", "message": "  Where is my receipt?  "})
        assert r.status_code == 422 and "email" in r.json()["error"]["details"]["fields"]
        r = await c.post("/api/support/messages", json={"topic": "other", "message": "Hello", "email": "guest@example.invalid"})
        assert r.status_code == 201, r.text
        r = await c.post("/api/support/messages", cookies=cookies(c, me),
                         json={"topic": "rewards", "message": "Points?", "email": "someone-else@example.invalid"})
        assert r.status_code == 201
        assert (await c.post("/api/support/messages", json={"topic": "spam", "message": "x", "email": "a@b.c"})).status_code == 400
    assert owner_sql(db, "SELECT user_id, email, topic, message FROM support_message ORDER BY id") == [
        (None, "guest@example.invalid", "other", "Hello"), (me, "asha@example.invalid", "rewards", "Points?")]

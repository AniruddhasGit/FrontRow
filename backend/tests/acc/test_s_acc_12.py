"""S-ACC-12 (P-ACC-11): a booking is upcoming before its showtime's ends_at and past from it, and each group is totally ordered."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.pay.kit import add_seats, api, book, clock_at, cookies, count, movie_and_showtime, owner_sql, user, world7

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    w = world7(migrated_db)
    movie_and_showtime(migrated_db, w, 20, "2026-08-20T08:30:00+00:00", ends="2026-08-20T11:05:00+00:00")
    movie_and_showtime(migrated_db, w, 21, "2026-08-21T08:30:00+00:00")
    movie_and_showtime(migrated_db, w, 22, "2026-08-22T08:30:00+00:00")
    add_seats(migrated_db, w["screen"], w["standard"], [(3000 + n, "K", n) for n in range(1, 6)], [20, 21, 22])
    return w


async def test_the_boundary_is_ends_at_on_the_injected_clock(world):
    db = world["db"]
    u = user(db)
    book(db, u, 20, [3001])
    for instant, group in [("2026-08-20T09:30:00+00:00", "upcoming"), ("2026-08-20T11:05:00+00:00", "past"),
                           ("2026-08-20T11:06:00+00:00", "past")]:
        async with api(db, clock_at(instant)) as c:
            body = (await c.get("/api/me/bookings", cookies=cookies(c, u))).json()
        rows = body["upcoming"] + body["past"]
        assert len(rows) == 1 and rows[0]["group"] == group, (instant, body)
        assert body[group] == rows


async def test_each_group_is_totally_ordered_and_pages_cleanly(world):
    db = world["db"]
    u = user(db)
    # Three share starts_at (showtime 21); created_at descending, then id ascending, break the tie.
    a, _ = book(db, u, 21, [3001], created_at="2026-08-12T10:00:00Z")
    b, _ = book(db, u, 21, [3002], created_at="2026-08-12T11:00:00Z")
    c_, _ = book(db, u, 21, [3003], created_at="2026-08-12T11:00:00Z")
    d, _ = book(db, u, 22, [3001], created_at="2026-08-12T09:00:00Z")
    e, _ = book(db, u, 20, [3004], created_at="2026-08-12T09:00:00Z")
    ref_of = dict(owner_sql(db, "SELECT id, 'FR-' || substr(reference, 1, 4) || '-' || substr(reference, 5) FROM booking"))
    upcoming = [e, b, c_, a, d]  # starts ascending; inside showtime 21: created desc (b, c tie) then id asc
    past = [d, b, c_, a, e]      # starts descending, the same tie-breakers
    for instant, group, want in [("2026-08-14T14:00:00+00:00", "upcoming", upcoming), ("2026-08-23T00:00:00+00:00", "past", past)]:
        async with api(db, clock_at(instant)) as c:
            full = (await c.get(f"/api/me/bookings?group={group}", cookies=cookies(c, u))).json()[group]
            assert [r["reference"] for r in full] == [ref_of[i] for i in want]
            paged = []
            for page in (1, 2, 3):
                paged += (await c.get(f"/api/me/bookings?group={group}&page={page}&page_size=2", cookies=cookies(c, u))).json()[group]
            assert [r["reference"] for r in paged] == [ref_of[i] for i in want]


def test_ends_at_is_stored_and_not_nullable(world):
    assert owner_sql(world["db"], "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
                                  "AND table_name='showtime' AND column_name='ends_at'") == [("NO",)]
    assert count(world["db"], "SELECT count(*) FROM showtime WHERE ends_at IS NULL") == 0


def test_this_module_never_reads_a_clock_or_sleeps():
    banned = "|".join([r"time\.time", r"time\.monotonic", r"time\.perf_counter", r"datetime\.now", r"datetime\.utcnow", r"sleep\("])
    assert not re.search(banned, Path(__file__).read_text(encoding="utf-8"))  # the escaped patterns cannot match themselves

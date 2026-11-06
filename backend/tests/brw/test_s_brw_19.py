"""S-BRW-19 (P-BRW-11/12, S7.4): the seat map is limited per address, and fails closed when Redis is gone.

Asserted: requests 1..120 from one address are 200 and the 121st is 429 RATE_LIMITED with an integer Retry-After in
1..60; with Redis unreachable the seat map is 503 DEPENDENCY_UNAVAILABLE with its one sentence while the movie and
showtime lists - not limited - are 200; the sentence's single occurrence in frontend/src.

NOT asserted (the row stays Blocked): the INCR-with-60-second-expiry counter and the seven-pollers-for-60-real-seconds
count of exactly 120/20. S7.4 specifies ONE limiter for every bucket - a token bucket in a Lua script on the injected
clock - and a token bucket refills continuously, so seven pollers over a real minute are mostly admitted; the
criterion describes a fixed window. PRD outranks Bible: filed as a doc defect. The 429-on-poll and 429-on-first-load
renders are the seat-map lane's (frontend/src/features/seatmap).
"""

from __future__ import annotations

import socket

import pytest

from tests.pay import kit
from tests.xct._support import rg

pytestmark = pytest.mark.anyio

DOWN = "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes."


async def test_the_121st_seat_map_read_in_a_minute_is_429_and_the_first_120_are_200(migrated_db):
    kit.world7(migrated_db)
    async with kit.api(migrated_db, kit.clock_at()) as c:
        rs = [await c.get(f"/api/showtimes/{kit.SHOWTIME}/seatmap") for _ in range(121)]
    assert [r.status_code for r in rs[:120]] == [200] * 120
    last = rs[120]
    assert (last.status_code, last.json()["error"]["code"]) == (429, "RATE_LIMITED")
    assert 1 <= int(last.headers["retry-after"]) <= 60


async def test_redis_unreachable_closes_the_seat_map_and_leaves_the_lists_open(migrated_db):
    w = kit.world7(migrated_db)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    async with kit.api(migrated_db, kit.clock_at(), REDIS_URL=f"redis://127.0.0.1:{port}/11") as c:
        seatmap = await c.get(f"/api/showtimes/{kit.SHOWTIME}/seatmap")
        movies = await c.get("/api/movies")
        showtimes = await c.get(f"/api/showtimes?movie_id={w['movie']}&date=2026-08-14")
    assert (seatmap.status_code, seatmap.json()["error"]["code"], seatmap.json()["error"]["message"]) == (
        503, "DEPENDENCY_UNAVAILABLE", DOWN)
    assert (movies.status_code, showtimes.status_code) == (200, 200), (movies.text, showtimes.text)
    assert len(rg(r"The seat map is unavailable right now\.", "frontend/src")) == 1

"""S-BRW-07 (P-BRW-05): the whole read path is public, identical for every caller, and reads no token.

Not here: GET /api/movies/{id}/poster (S-BRW-18, Blocked on the S3 SDK) and the guest's rendered seat map
(zero 'held by you' cells, no 2px border, the 'Sign in to hold these seats' action) - a browser harness. The
held-by-me computation the guest render rests on is unit-tested in frontend/src/features/seatmap.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.config import Settings
from app.core.security import SESSION_COOKIE, issue_session_token
from app.main import create_app
from tests.adm.kit import routes
from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_movie, make_screen, make_seat,
                           make_showtime, one, reset_catalogue, settings_for)
from tests.conftest import VALID_ENV
from tests.dbkit import FAKE_HASH

pytestmark = pytest.mark.anyio

READ_PATHS = {"/api/movies", "/api/movies/{movie_id}", "/api/showtimes", "/api/showtimes/{showtime_id}",
              "/api/showtimes/{showtime_id}/seatmap", "/api/reference"}


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_screen(db, make_cinema(db))
    make_seat(db, hall, "A", 1, 1, 1, make_category(db))
    film = make_movie(db)
    st = make_showtime(db, film, hall, "2026-08-16T19:30:00+05:30")
    return {"db": db, "film": film, "st": st}


def _urls(world) -> list[str]:
    f, s = world["film"], world["st"]
    return ["/api/movies", f"/api/movies/{f}", f"/api/showtimes?movie_id={f}", f"/api/showtimes/{s}",
            f"/api/showtimes/{s}/seatmap", "/api/reference"]


def test_every_read_route_carries_no_dependency():
    app = create_app(Settings(**VALID_ENV))
    found = {r.path: r for r in routes(app) if r.path in READ_PATHS}
    assert set(found) == READ_PATHS
    for path, route in found.items():
        assert route.dependant.dependencies == [], path


async def test_with_no_cookie_and_no_header_every_read_succeeds(world):
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(world["db"], clock) as c:
        for url in _urls(world):
            r = await c.get(url)
            assert r.status_code == 200, (url, r.text)


async def test_the_seatmap_is_byte_identical_for_a_guest_and_a_customer_and_an_expired_token_still_reads(world):
    db = world["db"]
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    user = one(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES ('c@example.invalid', %s, "
                   "'customer', 1) RETURNING id", (FAKE_HASH,))
    settings = settings_for(db)
    live = issue_session_token(user_id=user, role="customer", password_version=1, now=clock.now(), settings=settings)
    expired = issue_session_token(user_id=user, role="customer", password_version=1,
                                  now=clock.now() - timedelta(seconds=settings.SESSION_TTL_SECONDS + 60), settings=settings)
    url = f"/api/showtimes/{world['st']}/seatmap"
    async with api(db, clock) as c:
        guest = await c.get(url)
        customer = await c.get(url, cookies={SESSION_COOKIE: live})
        lapsed = [await c.get(u, cookies={SESSION_COOKIE: expired}) for u in _urls(world)]
    assert guest.status_code == customer.status_code == 200
    assert guest.content == customer.content
    assert [r.status_code for r in lapsed] == [200] * len(lapsed)

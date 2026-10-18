"""S-BRW-12 (P-BRW-09): three objective states on the wire; the fourth (held_by_me) is the client's.

Not here (browser harness): the rendered cells - data-glyph values under a one-colour stylesheet, computed
border styles, focus movement, the legend's swatches, the sold-out banner, the change ring on a fake timer.
The mapping from wire state + hold token to (fill, glyph, name) is unit-tested in frontend/src/features/seatmap.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.domain.browse.seatmap import Seat
from tests.brw.kit import (SetClock, api, book_seat, flush_redis, make_category, make_cinema, make_hall, make_movie,
                           make_showtime, redis_sync, reset_catalogue)

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_hall(db, make_cinema(db), rows=3, cols=14, categories=[make_category(db)] * 3)
    st = make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30", showtime_id=812)
    seats = hall["seats"]
    book_seat(db, 812, seats["C-12"])
    return {"db": db, "st": st, "seats": seats}


def _hold_c13(world) -> None:
    """Set right before the reads: a concurrent run of this suite flushing database 13 cannot remove it unseen."""
    r = redis_sync()
    try:
        r.set(f"lock:seat:812:{world['seats']['C-13']}", "a-hold-token", px=300_000)
    finally:
        r.close()


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


async def test_sold_held_available_and_byte_identical_for_two_callers(world):
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(world["db"], clock) as c:
        _hold_c13(world)
        first = await c.get("/api/showtimes/812/seatmap", cookies={"fr_session": "one-viewer"})
        second = await c.get("/api/showtimes/812/seatmap", cookies={"fr_session": "another-viewer"})
    assert first.status_code == 200 and first.content == second.content
    by_id = {s["id"]: s["state"] for s in first.json()["seats"]}
    s = world["seats"]
    assert (by_id[s["C-12"]], by_id[s["C-13"]], by_id[s["C-14"]]) == ("sold", "held", "available")
    assert {st for st in by_id.values()} <= {"available", "held", "sold"}
    names = _keys(json.loads(first.content))
    assert not [k for k in names if any(w in k for w in ("expires", "ttl", "remaining", "session", "request"))]


@pytest.mark.parametrize("state", ["held_by_me", "held_by_other", "blocked"])
def test_a_fourth_wire_state_is_refused_at_model_construction(state):
    with pytest.raises(ValidationError):
        Seat(id=1, row="C", num=12, gr=3, gc=12, cat=1, price_paise=25000, state=state, is_active=True)

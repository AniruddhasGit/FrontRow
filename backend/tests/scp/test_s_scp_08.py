"""S-SCP-08 (P-SCP-13, OPEN-SEAT-02/03/04): the seat map carries no accessible marking, no pair link, no gap rule.

The hold half (Phase 4): POST /api/showtimes/{id}/holds for seats 1 and 3 of a row with seat 2 free returning 201, and
the two-key SCAN after it (the fixture row is C, so the labels are C1 and C3).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_hall, make_movie, make_showtime,
                           owner_sql, reset_catalogue)
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio

TOKENS = re.compile(r"accessible|wheelchair|pair|couple|companion|gap|group", re.IGNORECASE)


def _contract_seat_keys() -> set[str]:
    contract = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))
    ep = next(e for e in contract["endpoints"] if e["path"] == "/api/showtimes/{showtime_id}/seatmap")
    seats = ep["responses"]["200"]["body"]["seats"]
    return {k.strip() for k in re.search(r"array of \{([^}]*)\}", seats).group(1).split(",")}


def test_the_contracts_seat_object_names_no_excluded_concept():
    keys = _contract_seat_keys()
    assert keys == {"id", "row", "num", "gr", "gc", "cat", "price_paise", "state", "is_active"}
    assert not [k for k in keys if TOKENS.search(k)]


async def test_a_live_seat_object_names_no_excluded_concept(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_hall(db, make_cinema(db), rows=1, cols=3, categories=[make_category(db)])
    st = make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30")
    async with api(db, SetClock()) as c:
        seats = (await c.get(f"/api/showtimes/{st}/seatmap")).json()["seats"]
    assert len(seats) == 3
    for seat in seats:
        assert set(seat) == _contract_seat_keys()
        assert not [k for k in seat if TOKENS.search(k)]


def test_the_seat_table_has_no_excluded_column(migrated_db):
    names = [r[0] for r in owner_sql(migrated_db, "SELECT column_name FROM information_schema.columns "
                                                  "WHERE table_schema = 'public' AND table_name = 'seat'")]
    assert names and not [n for n in names if TOKENS.search(n)]


async def test_two_seats_either_side_of_a_free_one_are_held_and_are_two_keys(migrated_db):
    """No gap rule: seats 1 and 3 of a row whose seat 2 is free are held together (201), and SCAN finds exactly
    the two per-seat keys - one key per seat, never one per group (P-HLD-08)."""
    from tests.sea.kit import T0, api as sea_api, redis_sync, session, user, world77

    world77(migrated_db)  # row C: 401 is C1, 402 is C2, 403 is C3
    customer = user(migrated_db)
    clock = SetClock()
    clock.set(T0)
    async with sea_api(migrated_db, clock) as c:
        r = await c.post("/api/showtimes/77/holds", json={"seat_ids": [401, 403]}, cookies=session(c, customer))
        client = redis_sync()
        try:
            keys = sorted(client.scan_iter(match="lock:seat:77:*"))
        finally:
            client.close()
    assert r.status_code == 201, r.text
    assert [s["label"] for s in r.json()["seats"]] == ["C1", "C3"]
    assert keys == ["lock:seat:77:401", "lock:seat:77:403"]

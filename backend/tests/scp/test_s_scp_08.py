"""S-SCP-08 (P-SCP-13, OPEN-SEAT-02/03/04): the seat map carries no accessible marking, no pair link, no gap rule.

Not here, and why the row stays Blocked: POST /api/showtimes/{id}/holds for A-01 and A-03 returning 201 and the
two-key SCAN after it - the hold endpoint is Phase 4 (E-SEA's hold rows).
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

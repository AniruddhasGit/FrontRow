"""S-BRW-13 (P-BRW-10): every category and every seat carries its already-rounded integer price.

Not here (browser harness): the rendered legend row 'Premium  $281.24', the inset block for a price not yet
arrived, the page text sweeps. The client's integer sum (3 x 33331 = 99993) and the formatter are unit-tested in
frontend/src/features/seatmap.
"""

from __future__ import annotations

import re

import pytest

from tests.brw.kit import SetClock, api, flush_redis, make_category, make_cinema, make_hall, make_movie, make_showtime, reset_catalogue
from tests.xct._support import rg

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    std, prem, recl = make_category(db, 0, "Standard"), make_category(db, 1250, "Premium"), make_category(db, 3333, "Recliner")
    hall = make_hall(db, make_cinema(db), rows=11, cols=20, categories=[std] * 6 + [prem] * 3 + [recl] * 2)
    st = make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30", price=24999)
    return {"db": db, "st": st, "cats": {std: 24999, prem: 28124, recl: 33331}}


async def test_the_three_worked_prices_and_every_seat_carries_its_categorys(world):
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(world["db"], clock) as c:
        r = await c.get(f"/api/showtimes/{world['st']}/seatmap")
    body = r.json()
    assert {cat["id"]: cat["price_paise"] for cat in body["categories"]} == world["cats"]
    assert len(body["seats"]) == 220
    for seat in body["seats"]:
        assert type(seat["price_paise"]) is int
        assert seat["price_paise"] == world["cats"][seat["cat"]]
    assert all(type(cat["price_paise"]) is int for cat in body["categories"])
    assert "$" not in r.text and "₹" not in r.text
    assert re.search(r"[0-9]+\.[0-9]", r.text) is None


def test_the_formula_module_uses_no_float_and_no_true_division():
    assert rg(r"float| / ", "backend/app/domain/pricing.py") == []

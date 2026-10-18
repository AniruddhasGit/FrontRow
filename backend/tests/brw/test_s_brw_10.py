"""S-BRW-10 (P-BRW-07, PROVISIONAL): a closed showtime is listed and marked, never hidden; the cut-off is one
signed configured value, derived at read time and never stored.

Not here, and why the row stays Blocked:
- SALES_CUTOFF_MINUTES UNSET must stop the boot. app/core/config.py (Zone B, the config lane's) gives it the
  default 15, which PRD S7.9 publishes; the criterion and S7.9 disagree. 'fifteen' IS refused, asserted below.
  The criterion also says stderr; the boot line goes to stdout by design (SRC-002 §7.6), asserted there.
- the closed button's tabindex / aria-disabled / Tab order / pathname, the closed seat map's banner, and the
  `rg -o 'Sales for this showtime have closed\\.' frontend/src | wc -l` count (that last one IS asserted here).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_movie, make_screen, make_seat,
                           make_showtime, owner_sql, reset_catalogue)
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR
from tests.xct._support import rg

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_screen(db, make_cinema(db))
    make_seat(db, hall, "A", 1, 1, 1, make_category(db))
    film = make_movie(db)
    st = make_showtime(db, film, hall, "2026-08-14T19:30:00+05:30")
    return {"db": db, "film": film, "st": st}


async def _flags(world, at: str, cutoff: str) -> list[tuple[str, bool]]:
    clock = SetClock()
    clock.set(at)
    async with api(world["db"], clock, SALES_CUTOFF_MINUTES=cutoff) as c:
        listed = (await c.get("/api/showtimes", params={"movie_id": world["film"], "date": "2026-08-14"})).json()["showtimes"][0]
        header = (await c.get(f"/api/showtimes/{world['st']}")).json()
        seatmap = (await c.get(f"/api/showtimes/{world['st']}/seatmap")).json()["showtime"]
    return [(o["sales_close_at"], o["sales_closed"]) for o in (listed, header, seatmap)]


async def test_plus_fifteen_closes_at_19_45_and_the_boundary_instant_is_closed(world):
    assert await _flags(world, "2026-08-14T19:44:59+05:30", "15") == [("2026-08-14T19:45:00+05:30", False)] * 3
    assert await _flags(world, "2026-08-14T19:45:00+05:30", "15") == [("2026-08-14T19:45:00+05:30", True)] * 3


async def test_minus_fifteen_is_the_other_reading_with_no_code_change(world):
    assert await _flags(world, "2026-08-14T19:20:00+05:30", "-15") == [("2026-08-14T19:15:00+05:30", True)] * 3


def test_sales_close_at_is_never_a_column(migrated_db):
    assert owner_sql(migrated_db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                                  "AND table_name = 'showtime' AND column_name = 'sales_close_at'") == [(0,)]


def test_a_non_integer_cut_off_stops_the_boot_naming_it(tmp_path):
    env = {**os.environ, **VALID_ENV, "SALES_CUTOFF_MINUTES": "fifteen", "PYTHONPATH": str(BACKEND_DIR)}
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0
    line = json.loads(proc.stdout.strip().splitlines()[-1])
    assert "SALES_CUTOFF_MINUTES" in line["missing_or_invalid"]


def test_the_banner_string_is_published_once_in_the_frontend():
    assert len(rg(r"Sales for this showtime have closed\.", "frontend/src")) == 1

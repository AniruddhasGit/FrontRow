"""S-BRW-15 (P-BRW-11): the server publishes the poll interval and the client holds no constant of its own.

The client's timer behaviour (one request per interval, one in flight, paused while hidden, the failure strip)
is unit-tested on a fake timer in frontend/src/features/seatmap/poller.test.mjs. Not here, and why the row
stays Blocked: SEATMAP_POLL_INTERVAL_SECONDS UNSET must stop the boot, but app/core/config.py (the config lane's)
defaults it to 3 as PRD S7.9 publishes - the criterion and S7.9 disagree. A non-integer IS refused, below.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tests.brw.kit import (SetClock, api, flush_redis, make_category, make_cinema, make_movie, make_screen, make_seat,
                           make_showtime, reset_catalogue)
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    hall = make_screen(db, make_cinema(db))
    make_seat(db, hall, "A", 1, 1, 1, make_category(db))
    return {"db": db, "st": make_showtime(db, make_movie(db), hall, "2026-08-16T19:30:00+05:30")}


@pytest.mark.parametrize("configured,published", [(None, 3), ("5", 5)])
async def test_the_payload_carries_the_configured_interval(world, configured, published):
    overrides = {} if configured is None else {"SEATMAP_POLL_INTERVAL_SECONDS": configured}
    async with api(world["db"], SetClock(), **overrides) as c:
        body = (await c.get(f"/api/showtimes/{world['st']}/seatmap")).json()
    assert body["poll_interval_seconds"] == published and type(body["poll_interval_seconds"]) is int


def test_a_non_integer_interval_stops_the_boot_naming_it(tmp_path):
    env = {**os.environ, **VALID_ENV, "SEATMAP_POLL_INTERVAL_SECONDS": "three", "PYTHONPATH": str(BACKEND_DIR)}
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0
    assert "SEATMAP_POLL_INTERVAL_SECONDS" in json.loads(proc.stdout.strip().splitlines()[-1])["missing_or_invalid"]

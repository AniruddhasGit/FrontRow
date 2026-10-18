"""S-BRW-17 (P-BRW-13, P-BRW-14): nothing is paginated, no latency number is invented, and Phase 3 measured.

Not here (browser harness): the seat-map frame's rects before and after the response, and the absence of a
progressbar or 'Loading' name at either point.
"""

from __future__ import annotations

import csv

import pytest

from app.core.config import Settings
from app.main import create_app
from tests.brw.kit import SetClock, api, flush_redis, make_category, make_cinema, make_hall, make_movie, make_showtime, reset_catalogue
from tests.conftest import VALID_ENV
from tests.xct._support import REPO, rg

pytestmark = pytest.mark.anyio

MEASUREMENTS = REPO / "docs" / "10 EngineeringLedger" / "PHASE3_MEASUREMENTS.tsv"


def test_no_browse_endpoint_declares_a_pagination_parameter():
    doc = create_app(Settings(**VALID_ENV)).openapi()
    browse = {p: ops for p, ops in doc["paths"].items() if p.startswith(("/api/movies", "/api/showtimes", "/api/reference"))}
    assert {"/api/movies", "/api/showtimes", "/api/reference", "/api/showtimes/{showtime_id}/seatmap"} <= set(browse)
    names = {param["name"] for ops in browse.values() for op in ops.values() for param in op.get("parameters", [])}
    assert names and not names & {"page", "offset", "limit", "cursor"}


async def test_page_and_limit_are_ignored_and_nothing_is_capped(migrated_db):
    reset_catalogue(migrated_db)
    flush_redis()
    db = migrated_db
    for _ in range(12):
        make_movie(db)
    hall = make_hall(db, make_cinema(db), rows=11, cols=20, categories=[make_category(db)] * 11)
    st = make_showtime(db, make_movie(db), hall["screen_id"], "2026-08-16T19:30:00+05:30")
    clock = SetClock()
    clock.set("2026-08-15T12:00:00+05:30")
    async with api(db, clock) as c:
        plain = await c.get("/api/movies")
        paged = await c.get("/api/movies", params={"page": "2", "limit": "5"})
        seats = (await c.get(f"/api/showtimes/{st}/seatmap")).json()["seats"]
    assert paged.content == plain.content and plain.json()["count"] == 13 == len(plain.json()["movies"])
    assert len(seats) == 220


def test_no_latency_budget_is_written_anywhere():
    assert rg(r"p50|p95|p99|ttfb|time_to_first_byte|frames_per_second|\bfps\b", "backend/app", "frontend/src") == []


def test_the_phase3_measurement_exists_with_a_real_sample_per_metric():
    rows = list(csv.reader(MEASUREMENTS.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
    assert rows[0] == ["Metric", "Worst", "Median", "Samples", "Method"]
    by_metric = {r[0]: r for r in rows[1:]}
    for metric in ("seatmap_response_bytes", "seatmap_response_ms", "seatmap_cache_hit_rate"):
        row = by_metric[metric]
        assert int(row[3]) >= 1
        assert row[1].strip() and row[1].strip() != "TBD"

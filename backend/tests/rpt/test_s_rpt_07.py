"""S-RPT-07 - occupancy is capacity-weighted, integer half-up, over seat_count_at_creation (P-RPT-04)."""

from __future__ import annotations

import re

import pytest

from app.domain.reports import occupancy
from tests.rpt.kit import DAY, client, get, owner_sql, prd_world, show  # noqa: F401


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def tenths(sold, cap):
    return (sold * 2000 + cap) // (2 * cap) / 10


@pytest.mark.parametrize("sold, cap, expected", [(97, 150, 64.7), (12, 220, 5.5), (109, 370, 29.5), (1, 16, 6.3)])
def test_the_integer_half_up_rule(sold, cap, expected):
    assert occupancy(sold, cap) == tenths(sold, cap) == expected
    if (sold, cap) == (1, 16):
        assert round(sold / cap * 100, 1) == 6.2  # the float implementation gives the wrong answer here


def test_the_capacity_weighted_aggregate(client, world):
    body = get(client, world["M"], DAY).json()
    assert (body["seats_sold"], body["capacity"], body["occupancy_pct"]) == (109, 370, 29.5)
    assert body["occupancy_pct"] != round((64.7 + 5.5) / 2, 1) == 35.1


def test_the_denominator_is_frozen_at_creation(client, world):
    owner_sql(world["db"], "UPDATE seat SET is_active = false WHERE id IN (SELECT id FROM seat WHERE screen_id = 3 ORDER BY id LIMIT 3)")
    try:
        body = get(client, world["M"], DAY).json()
    finally:
        owner_sql(world["db"], "UPDATE seat SET is_active = true WHERE screen_id = 3")
    assert (body["capacity"], body["occupancy_pct"]) == (370, 29.5)


def test_capacity_zero_is_null(client, world):
    body = get(client, world["M"], "/api/reports/dashboard?period=day&date=2026-09-30").json()
    assert (body["capacity"], body["occupancy_pct"]) == (0, None)


def test_an_unsold_show_still_counts_its_capacity(client, world):
    show(world, 106, 3, 1, "2026-08-14T10:00:00Z")
    body = get(client, world["M"], DAY).json()
    assert (body["capacity"], body["occupancy_pct"]) == (520, 21.0)


def test_a_zero_denominator_is_a_500_with_no_occupancy_key(client, world):
    owner_sql(world["db"], "UPDATE showtime SET seat_count_at_creation = 0 WHERE id = 106")
    try:
        r = get(client, world["M"], DAY)
    finally:
        owner_sql(world["db"], "UPDATE showtime SET seat_count_at_creation = 150 WHERE id = 106")
    assert r.status_code == 500 and "occupancy_pct" not in r.text
    rid = r.json()["error"]["request_id"]
    assert re.fullmatch(r"[0-9a-f]{8}", rid) and rid == r.headers["x-request-id"]
    assert r.json()["error"] == {"code": "INTERNAL_ERROR", "details": {}, "request_id": rid,
                                 "message": f"This period's figures could not be loaded. If you need help, quote {rid}."}

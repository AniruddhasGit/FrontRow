"""S-RPT-06 - takings are the sum of snapshotted per-seat prices, integer paise, confirmed + captured only (P-RPT-03).
The rendered form (the takings figure on /dashboard reading ₹27,833.31) is asserted in
frontend/src/features/reports/reports.test.mjs."""

from __future__ import annotations

import json
import re

import pytest

from app.core.security import SESSION_COOKIE, issue_session_token
from tests.rpt.kit import DAY, client, get, owner_sql, prd_world, sell, settings, takings_sql  # noqa: F401

STANDARD = (25000 * 10000 + 5000) // 10000
PREMIUM = (25000 * 13333 + 5000) // 10000


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_the_worked_example(client, world):
    assert (STANDARD, PREMIUM) == (25000, 33333)
    r = get(client, world["M"], DAY)
    body = json.loads(r.text)
    assert body["takings_paise"] == 2783331 == 90 * STANDARD + 7 * PREMIUM + 12 * STANDARD
    assert body["takings_paise"] == takings_sql(world["db"], (3, 5))
    assert isinstance(body["takings_paise"], int)
    admin = get(client, world["admin"], DAY).json()
    assert admin["takings_paise"] > body["takings_paise"]  # ST-103 (screen 1) is out of M's scope, not out of the data
    for s in _strings(body):
        assert "₹" not in s and not re.search(r"\d+\.\d{2}", s), s


def test_a_period_with_no_sales_is_zero_not_null(client, world):
    body = get(client, world["M"], "/api/reports/dashboard?period=day&date=2026-08-21").json()
    assert body["takings_paise"] == 0 and isinstance(body["takings_paise"], int)


def test_saturday_holds_st_104_and_friday_does_not(client, world):
    sat = get(client, world["M"], "/api/reports/dashboard?period=day&date=2026-08-15").json()
    assert sat["takings_paise"] == 40 * 25000


def test_a_live_hold_and_a_failed_payment_add_nothing_three_captured_seats_add_75000(client, world):
    token = issue_session_token(user_id=world["customer"], role="customer", password_version=1, now=client.app.state.clock.now(),
                                settings=settings(client.db))
    free = [r[0] for r in owner_sql(world["db"], """
        SELECT ss.seat_id FROM showtime_seat ss WHERE ss.showtime_id = 101 AND NOT EXISTS
        (SELECT 1 FROM booking_seat bs WHERE bs.showtime_id = 101 AND bs.seat_id = ss.seat_id) ORDER BY 1 DESC LIMIT 2""")]
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token)
    held = client.post("/api/showtimes/101/holds", json={"seat_ids": free})
    assert held.status_code == 201, held.text  # a live 2-seat hold exists now
    assert get(client, world["M"], DAY).json()["takings_paise"] == 2783331
    sell(world, 101, 3, 25000)
    assert get(client, world["M"], DAY).json()["takings_paise"] == 2783331 + 75000 == 2858331

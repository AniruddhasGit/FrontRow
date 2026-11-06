"""S-RPT-04 - screen scope proved with both halves: a non-empty non-zero figure for the manager's own hall that is
strictly less than the administrator's, and a refusal for another hall (P-RPT-02's test shape)."""

from __future__ import annotations

import pytest

from tests.rpt.kit import DAY, assign, client, film, get, sell, show, takings_sql, user_row, venue  # noqa: F401


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {1: 30, 2: 30})
    m = film(w, "DEMO MOVIE 01")
    show(w, 201, 1, m, "2026-08-14T14:00:00Z")
    show(w, 202, 2, m, "2026-08-14T15:00:00Z")
    sell(w, 201, 10, (25000 * 10000 + 5000) // 10000)  # FR-ADR-038 at 0 bp = 25000
    sell(w, 202, 4, 25000)
    w["admin"], w["A"], w["B"] = user_row(migrated_db, "admin"), user_row(migrated_db, "manager"), user_row(migrated_db, "manager")
    assign(migrated_db, w["A"], 1)
    return w


def test_both_halves_in_one_test(client, world):
    own = get(client, world["A"], DAY).json()
    assert own["takings_paise"] == 250000 and own["takings_paise"] > 0
    assert own["seats_sold"] == 10 and own["seats_sold"] > 0
    assert own["takings_paise"] == takings_sql(world["db"], (1,))
    admin = get(client, world["admin"], DAY).json()
    assert own["takings_paise"] < admin["takings_paise"] == 350000
    denied = get(client, world["A"], DAY + "&screen_id=2")
    assert denied.status_code == 403
    assert (denied.json()["error"]["code"], denied.json()["error"]["message"]) == ("FORBIDDEN", "That hall is not assigned to this account.")
    assert {1, 2} <= set(admin["screen_ids"]) and (admin["seats_sold"], admin["takings_paise"]) == (14, 350000)
    empty = get(client, world["B"], DAY)
    assert empty.status_code == 200
    assert (empty.json()["scope_empty"], empty.json()["takings_paise"]) == (True, 0)

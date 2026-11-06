"""S-XCT-11 - a manager's screen scope is resolved from the session and never from the request (P-XCT-05, FR-ADR-011).

The rg clause's path backend/app/api/routes/reports.py does not exist (SRC-002 §11.1: routers sit directly under
backend/app/api; the same correction the Bible amendments made for S-XCT-10 and S-XCT-12), so it is run over
backend/app/api/reports, where the reports router lives."""

from __future__ import annotations

import pytest
from sqlalchemy import event

from tests.rpt.kit import assign, film, get, make_client, sell, show, user_row, venue
from tests.xct._support import rg

D = "/api/reports/dashboard?period=day&date=2026-08-14"


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {2: 20, 4: 20, 5: 20})
    m = film(w, "DEMO MOVIE 01")
    for sid, screen in ((1102, 2), (1104, 4), (1105, 5)):
        show(w, sid, screen, m, "2026-08-14T14:00:00Z")
        sell(w, sid, 3, 25000)
    user_row(migrated_db, "manager", user_id=88)
    assign(migrated_db, 88, 2, 5)
    w["admin"], w["new"] = user_row(migrated_db, "admin"), user_row(migrated_db, "manager")
    return w


def test_the_scope_comes_from_the_session_and_reaches_the_where_clause(world):
    seen = []
    with make_client(world["db"]) as c:
        event.listen(c.app.state.db_engine.sync_engine, "before_cursor_execute",
                     lambda conn, cur, stmt, params, ctx, many: seen.append((stmt, params)))
        own = get(c, 88, D)
        narrowed = get(c, 88, D + "&screen_id=2")
        other = get(c, 88, D + "&screen_id=4")
        post = c.post("/api/reports/dashboard")
    assert own.status_code == 200 and own.json()["screen_ids"] == [2, 5] and own.json()["takings_paise"] == 150000
    assert narrowed.status_code == 200 and narrowed.json()["takings_paise"] == 75000 > 0
    assert other.status_code == 403 and other.json()["error"]["code"] == "FORBIDDEN"
    assert post.status_code == 405 and post.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    figures = [p for s, p in seen if "booking_seat" in s and isinstance(p, dict) and "screen_ids" in p]
    assert figures and tuple(figures[0]["screen_ids"]) == (2, 5)
    assert "2" not in [tok for s, _ in seen if "booking_seat" in s for tok in s.split()]  # parameterised, not inlined
    assert rg(r"if .*screen_id|filter\(lambda", "backend/app/api/reports") == []


def test_an_unassigned_manager_gets_an_empty_200_and_the_admin_sees_everything(world):
    with make_client(world["db"]) as c:
        empty = get(c, world["new"], D)
        admin = [get(c, world["admin"], D + q) for q in ("", "&screen_id=2", "&screen_id=4")]
    assert empty.status_code == 200 and (empty.json()["scope_empty"], empty.json()["takings_paise"]) == (True, 0)
    assert [r.status_code for r in admin] == [200, 200, 200]
    assert [r.json()["takings_paise"] for r in admin] == [225000, 75000, 75000]

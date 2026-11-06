"""S-RPT-02 - period and date validation; boundary instants bare UTC, rendered instants with the cinema offset.
The two frontend clauses (no _utc field in frontend/src/features/reports, no bare-UTC text node in the rendered
screens) are asserted in frontend/src/features/reports/reports.test.mjs."""

from __future__ import annotations

import pytest

from tests.rpt.kit import INSTANT, client, film, get, owner_sql, show, user_row, venue  # noqa: F401


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {3: 20})
    m = film(w, "DEMO MOVIE 01")
    show(w, 101, 3, m, "2026-08-14T14:00:00Z")
    w["admin"] = user_row(migrated_db, "admin")
    owner_sql(migrated_db, "INSERT INTO audit_log (occurred_at, actor_user_id, actor_role, action, entity_type, entity_id, "
                           "before, after, request_id) VALUES ('2026-08-12T10:10:00Z', %s, 'admin', 'showtime.base_price_changed', "
                           "'showtime', 101, '{\"base_price_paise\": 25000}', '{\"base_price_paise\": 30000}', 'a1b2c3d4')",
              (w["admin"],))
    return w


@pytest.mark.parametrize("query, message", [
    ("", "Choose day, week or month."),
    ("?period=year", "Choose day, week or month."),
    ("?period=day&date=14-08-2026", "The date must be written as YYYY-MM-DD."),
    ("?period=day&date=2026-02-30", "That date does not exist."),
])
def test_bad_period_and_date_are_422(client, world, query, message):
    r = get(client, world["admin"], "/api/reports/dashboard" + query)
    assert r.status_code == 422
    assert (r.json()["error"]["code"], r.json()["error"]["message"]) == ("VALIDATION_FAILED", message)


@pytest.mark.parametrize("anchor", ["1990-01-01", "2099-01-01"])
def test_no_bound_on_the_anchor_in_either_direction(client, world, anchor):
    body = get(client, world["admin"], f"/api/reports/dashboard?period=day&date={anchor}").json()
    for key in ("period_start_utc", "period_end_utc", "evaluated_at_utc"):
        assert INSTANT.fullmatch(body[key]), (key, body[key])


def test_rendered_instants_carry_the_offset_and_no_utc_suffix(client, world):
    a = world["admin"]
    st = get(client, a, "/api/reports/showtimes?period=day&date=2026-08-14").json()
    assert st["rows"][0]["starts_at"] == "2026-08-14T19:30:00+05:30" and st["timezone"] == "Asia/Kolkata"
    log = get(client, a, "/api/reports/audit?from=2026-08-12&to=2026-08-12").json()
    assert log["rows"][0]["occurred_at"] == "2026-08-12T15:40:00+05:30" and log["timezone"] == "Asia/Kolkata"
    assert not any(k.endswith("_utc") for k in st["rows"][0]) and not any(k.endswith("_utc") for k in log["rows"][0])

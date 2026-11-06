"""S-RPT-01 - the reporting period is a whole local period in the cinema row's zone, converted to UTC from the
injected clock (P-RPT-01)."""

from __future__ import annotations

import pytest

from tests.xct._support import rg
from tests.rpt.kit import client, film, get, owner_sql, sell, show, user_row, venue  # noqa: F401


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {1: 20})
    m = film(w, "DEMO MOVIE 01")
    show(w, 501, 1, m, "2026-08-14T19:00:00Z")  # Sat 15 Aug 00:30 local
    sell(w, 501, 2, 25000)
    w["admin"] = user_row(migrated_db, "admin")
    return w


def window(body):
    return body["period_start_utc"], body["period_end_utc"]


def test_day_week_month_windows_from_the_injected_clock(client, world):
    a = world["admin"]
    assert window(get(client, a, "/api/reports/dashboard?period=day").json()) == ("2026-08-13T18:30:00Z", "2026-08-14T18:30:00Z")
    assert window(get(client, a, "/api/reports/dashboard?period=week").json()) == ("2026-08-09T18:30:00Z", "2026-08-16T18:30:00Z")
    assert window(get(client, a, "/api/reports/dashboard?period=month").json()) == ("2026-07-31T18:30:00Z", "2026-08-31T18:30:00Z")


def test_the_interval_is_half_open_so_a_late_show_belongs_to_the_next_local_day(client, world):
    a = world["admin"]
    friday = get(client, a, "/api/reports/dashboard?period=day&date=2026-08-14").json()
    saturday = get(client, a, "/api/reports/dashboard?period=day&date=2026-08-15").json()
    assert (friday["shows"], friday["takings_paise"]) == (0, 0)
    assert (saturday["shows"], saturday["takings_paise"]) == (1, 50000)


def test_the_zone_is_read_from_the_cinema_row(client, world):
    a = world["admin"]
    try:
        owner_sql(world["db"], "UPDATE cinema SET timezone = 'UTC' WHERE id = 1")  # the column EP-ADM-29 writes
        body = get(client, a, "/api/reports/dashboard?period=day").json()
        assert window(body) == ("2026-08-14T00:00:00Z", "2026-08-15T00:00:00Z") and body["timezone"] == "UTC"
    finally:
        owner_sql(world["db"], "UPDATE cinema SET timezone = 'Asia/Kolkata' WHERE id = 1")
    body = get(client, a, "/api/reports/dashboard?period=day").json()
    assert body["period_start_utc"] == "2026-08-13T18:30:00Z" and body["timezone"] == "Asia/Kolkata"


def _rg(pattern: str) -> list:
    return rg(pattern, "backend/app/api/reports", "backend/app/domain/reports")


def test_no_wall_clock_and_no_database_clock_on_this_surface():
    assert _rg(r"datetime\.now|utcnow|time\.time\(|date\.today\(") == []
    assert _rg(r"datetime\.now\(\)|datetime\.utcnow|CURRENT_DATE|CURRENT_TIMESTAMP|LOCALTIMESTAMP") == []

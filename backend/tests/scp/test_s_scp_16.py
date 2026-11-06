"""S-SCP-16 - the dashboard offers no export, download or print-to-file path (P-SCP-14, P-RPT-10).

Backend half here; the rendered-screen half (no control named export|download|csv|..., no a[download]) is in
frontend/src/test/reports_absence.test.mjs."""

from __future__ import annotations

import pytest

from tests.rpt.kit import client, get, prd_world  # noqa: F401


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


@pytest.mark.parametrize("url", ["/api/reports/dashboard?period=day", "/api/reports/showtimes?period=day",
                                 "/api/reports/scope", "/api/reports/audit"])
def test_json_utf8_and_no_content_disposition(client, world, url):
    r = get(client, world["admin"], url)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert "content-disposition" not in r.headers


@pytest.mark.parametrize("url", ["/api/reports/dashboard.csv", "/api/reports/export", "/api/admin/bookings.csv"])
def test_no_export_address_exists(client, world, url):
    r = get(client, world["admin"], url)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"

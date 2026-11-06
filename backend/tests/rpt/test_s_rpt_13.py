"""S-RPT-13 - no export of any kind, and no customer-level row from any reports endpoint (P-RPT-10).
The two frontend rg clauses are asserted in frontend/src/test/reports_absence.test.mjs."""

from __future__ import annotations

import pytest

from tests.adm.kit import routes
from tests.rpt.kit import DAY, client, get, owner_sql, prd_world  # noqa: F401

FOUR = [DAY, "/api/reports/showtimes?period=day&date=2026-08-14&limit=50&offset=0", "/api/reports/scope",
        "/api/reports/audit?from=2026-08-12&to=2026-08-12"]


@pytest.fixture(scope="module")
def world(migrated_db):
    w = prd_world(migrated_db)
    owner_sql(migrated_db, "INSERT INTO audit_log (occurred_at, actor_user_id, actor_role, action, entity_type, entity_id, "
                           "before, after, request_id) VALUES ('2026-08-12T10:10:00Z', %s, 'admin', 'showtime.base_price_changed', "
                           "'showtime', 101, '{\"base_price_paise\": 25000}', '{\"base_price_paise\": 30000}', 'a1b2c3d4')",
              (w["admin"],))
    return w


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_no_content_disposition_and_json_only(client, world):
    for url in FOUR:
        r = get(client, world["admin"], url)
        assert r.status_code == 200, url
        assert "content-disposition" not in r.headers, url
    r = get(client, world["admin"], "/api/reports/dashboard?period=day", headers={"Accept": "text/csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")


def test_no_csv_path(client, world):
    assert get(client, world["admin"], "/api/reports/dashboard.csv").status_code == 404
    assert [r.path for r in routes(client.app) if r.path.endswith(".csv")] == []


def test_no_customer_name_email_or_reference_anywhere(client, world):
    db = world["db"]
    emails = {r[0] for r in owner_sql(db, "SELECT email FROM users WHERE role = 'customer'")}
    secrets = emails | {e.split("@")[0] for e in emails} | {r[0] for r in owner_sql(db, "SELECT reference FROM booking")}
    assert len(secrets) > 10  # not vacuous: every seeded customer and booking reference
    for url in FOUR:
        found = [s for s in _strings(get(client, world["admin"], url).json()) for x in secrets if x in s]
        assert found == [], url

"""S-RPT-14 - the administrator-only change log, filtered and cursor-paginated (P-RPT-11)."""

from __future__ import annotations

import pytest

from tests.rpt.kit import client, get, one, owner_sql, user_row, venue  # noqa: F401

URL = "/api/reports/audit?from=2026-08-12&to=2026-08-12"


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {1: 10})
    w["admin"] = user_row(migrated_db, "admin", email="admin-a@example.invalid")
    w["M"], w["customer"] = user_row(migrated_db, "manager"), user_row(migrated_db, "customer")
    ins = ("INSERT INTO audit_log (id, occurred_at, actor_user_id, actor_role, action, entity_type, entity_id, before, after, "
           "request_id) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, 'admin', %s, %s, %s, %s, %s, 'a1b2c3d4')")
    owner_sql(migrated_db, ins, (5, "2026-08-12T10:10:00Z", w["admin"], "showtime.base_price_changed", "showtime", 101,
                                 '{"base_price_paise": 25000}', '{"base_price_paise": 30000}'))
    owner_sql(migrated_db, ins, (4, "2026-08-12T05:00:00Z", w["admin"], "movie.published", "movie", 3, None, '{"published": true}'))
    owner_sql(migrated_db, ins, (3, "2026-08-12T04:00:00Z", w["admin"], "movie.published", "movie", 2, None, '{"published": true}'))
    owner_sql(migrated_db, ins, (2, "2026-07-20T04:00:00Z", w["admin"], "movie.published", "movie", 1, None, '{"published": true}'))
    return w


def err(r):
    return r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]


def test_the_worked_example(client, world):
    body = get(client, world["admin"], URL + "&action=showtime.base_price_changed").json()
    assert (body["window_start_utc"], body["window_end_utc"]) == ("2026-08-11T18:30:00Z", "2026-08-12T18:30:00Z")
    (row,) = body["rows"]
    assert row == {"id": 5, "occurred_at": "2026-08-12T15:40:00+05:30", "actor_user_id": world["admin"],
                   "actor_email": "admin-a@example.invalid", "actor_role": "admin", "action": "showtime.base_price_changed",
                   "entity_type": "showtime", "entity_id": 101, "before": {"base_price_paise": 25000},
                   "after": {"base_price_paise": 30000}, "request_id": "a1b2c3d4"}
    assert body["rows"][0]["after"] == {"base_price_paise": 30000}


def test_roles(client, world):
    assert err(get(client, world["M"], URL)) == (403, "FORBIDDEN", "This page is for administrators.")
    assert err(get(client, world["customer"], URL)) == (403, "FORBIDDEN", "This page is for administrators.")
    r = get(client, None, URL)
    assert (r.status_code, r.json()["error"]["code"]) == (401, "AUTH_REQUIRED")


def test_newest_first_and_the_cursor(client, world):
    a = get(client, world["admin"], URL + "&limit=2").json()
    assert [r["id"] for r in a["rows"]] == [5, 4] and a["next_cursor"] == 4
    b = get(client, world["admin"], URL + "&limit=2&cursor=4").json()
    assert [r["id"] for r in b["rows"]] == [3] and b["next_cursor"] is None
    c = get(client, world["admin"], URL + "&cursor=999999")
    assert c.status_code == 200 and [r["id"] for r in c.json()["rows"]] == [5, 4, 3] and "message" not in c.json()


@pytest.mark.parametrize("query, message", [
    ("/api/reports/audit?from=2026-08-13&to=2026-08-12", "The start date must be on or before the end date."),
    ("/api/reports/audit?from=12-08-2026", "The date must be written as YYYY-MM-DD."),
    (URL + "&limit=0", "Ask for between 1 and 200 rows."),
    (URL + "&limit=201", "Ask for between 1 and 200 rows."),
    (URL + "&entity_id=101", "Choose a record type before filtering by record id."),
    (URL + "&cursor=0", "That page of results is no longer valid. Start again from the newest change."),
    (URL + "&cursor=abc", "That page of results is no longer valid. Start again from the newest change."),
])
def test_validation(client, world, query, message):
    assert err(get(client, world["admin"], query)) == (422, "VALIDATION_FAILED", message)


def test_non_members_return_an_empty_page(client, world):
    for q in ("&action=movie.renamed", "&actor_user_id=987654"):
        r = get(client, world["admin"], URL + q)
        assert r.status_code == 200 and r.json()["rows"] == []


def test_the_default_window_is_thirty_days_from_the_injected_clock(client, world):
    body = get(client, world["admin"], "/api/reports/audit").json()
    assert (body["window_start_utc"], body["window_end_utc"]) == ("2026-07-14T18:30:00Z", "2026-08-14T18:30:00Z")
    assert [r["id"] for r in body["rows"]] == [5, 4, 3, 2]


def test_reading_the_log_is_not_audited(client, world):
    before = one(world["db"], "SELECT count(*) FROM audit_log")
    for q in ("", "?from=2026-08-13&to=2026-08-12", "?cursor=abc", "?action=showtime.base_price_changed"):
        get(client, world["admin"], "/api/reports/audit" + q)
        get(client, world["M"], "/api/reports/audit" + q)
    assert one(world["db"], "SELECT count(*) FROM audit_log") == before

"""S-RPT-15 - both change-log option sets derive from the date window alone (P-RPT-11)."""

from __future__ import annotations

import json

import pytest

from tests.rpt.kit import client, get, owner_sql, user_row, venue  # noqa: F401

DAY12 = "/api/reports/audit?from=2026-08-12&to=2026-08-12"


@pytest.fixture(scope="module")
def world(migrated_db):
    w = venue(migrated_db, {1: 10})
    for uid, email in ((1, "admin-a@example.invalid"), (4, "admin-b@example.invalid"), (7, "admin-c@example.invalid"),
                       (9, "admin-d@example.invalid")):
        user_row(migrated_db, "admin", user_id=uid, email=email)
    ins = ("INSERT INTO audit_log (id, occurred_at, actor_user_id, actor_role, action, entity_type, entity_id, before, after, "
           "request_id) OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s, 'movie', 1, NULL, '{}', 'a1b2c3d4')")
    owner_sql(migrated_db, ins, (31, "2026-08-12T10:10:00Z", 1, "admin", "showtime.base_price_changed"))
    owner_sql(migrated_db, ins, (30, "2026-08-12T05:35:00Z", 1, "manager", "movie.published"))
    owner_sql(migrated_db, ins, (29, "2026-08-12T03:50:00Z", 4, "admin", "movie.published"))
    owner_sql(migrated_db, ins, (12, "2026-08-03T05:00:00Z", 7, "admin", "movie.unpublished"))
    return w  # account 9 is an administrator holding no audit_log row at all


def sets(body):
    return json.dumps(body["available_actions"]), json.dumps(body["available_actors"])


def test_the_window_decides_the_options_and_the_filter_decides_the_rows(client, world):
    a = get(client, 9, DAY12 + "&action=showtime.base_price_changed").json()
    assert len(a["rows"]) == 1
    assert a["available_actions"] == ["movie.published", "showtime.base_price_changed"]
    assert a["available_actors"] == [{"actor_user_id": 1, "actor_email": "admin-a@example.invalid"},
                                     {"actor_user_id": 4, "actor_email": "admin-b@example.invalid"}]
    b = get(client, 9, DAY12 + "&action=showtime.base_price_changed&actor_user_id=4").json()
    assert b["rows"] == [] and sets(b) == sets(a)
    c = get(client, 9, DAY12 + "&limit=1&cursor=30").json()
    assert [r["id"] for r in c["rows"]] == [29] and sets(c) == sets(a)
    assert all(set(x) == {"actor_user_id", "actor_email"} for x in a["available_actors"])


def test_only_the_dates_move_the_sets(client, world):
    empty = get(client, 9, "/api/reports/audit?from=2026-08-13&to=2026-08-13").json()
    assert (empty["available_actions"], empty["available_actors"]) == ([], [])
    wide = get(client, 9, "/api/reports/audit?from=2026-08-01&to=2026-08-12").json()
    assert wide["available_actions"] == ["movie.published", "movie.unpublished", "showtime.base_price_changed"]
    assert [x["actor_user_id"] for x in wide["available_actors"]] == [1, 4, 7]
    assert "screen.deactivated" not in wide["available_actions"]
    assert 9 not in [x["actor_user_id"] for x in wide["available_actors"]]


def test_one_account_under_two_roles_is_one_option(client, world):
    body = get(client, 9, DAY12).json()
    assert [x["actor_user_id"] for x in body["available_actors"]].count(1) == 1
    assert sorted(r["actor_role"] for r in body["rows"] if r["actor_user_id"] == 1) == ["admin", "manager"]

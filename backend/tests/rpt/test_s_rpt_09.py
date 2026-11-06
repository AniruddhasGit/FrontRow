"""S-RPT-09 - EP-RPT-01 is served from ONE snapshot: a complete period or nothing (P-RPT-07)."""

from __future__ import annotations

import re

import pytest

from app.domain import reports as rpt
from tests.rpt.kit import DAY, ServerLog, get, make_client, prd_world, sell

KEYS = sorted(["period", "period_start_utc", "period_end_utc", "evaluated_at_utc", "timezone", "scope_empty", "screen_ids",
               "takings_paise", "seats_sold", "capacity", "occupancy_pct", "shows", "films", "films_truncated"])


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def test_the_request_runs_at_repeatable_read_and_has_the_exact_key_set(world):
    log = ServerLog(world["db"])
    with make_client(world["db"]) as c:
        log.attach(c)
        log.lines.clear()
        body = get(c, world["M"], DAY).json()
    assert [s for s in log.statements() if s.startswith("BEGIN") and "ISOLATION LEVEL REPEATABLE READ" in s], log.statements()
    assert sorted(body.keys()) == KEYS
    assert body["takings_paise"] == 2783331 and len(body["films"]) == 1 and body["films"][0]["takings_paise"] == 2783331
    assert body["films_truncated"] is False
    assert sum(f["takings_paise"] for f in body["films"]) == body["takings_paise"]
    assert sum(f["seats_sold"] for f in body["films"]) == body["seats_sold"]


def test_a_booking_committed_between_the_two_queries_is_in_neither(world, monkeypatch):
    original = rpt.films

    async def commit_then_films(*args, **kwargs):
        sell(world, 101, 1, 25000)  # a second connection, committed between the headline and the per-film query
        return await original(*args, **kwargs)

    monkeypatch.setattr(rpt, "films", commit_then_films)
    with make_client(world["db"]) as c:
        body = get(c, world["M"], DAY).json()
        monkeypatch.setattr(rpt, "films", original)
        after = get(c, world["M"], DAY).json()
    assert body["takings_paise"] == 2783331
    assert sum(f["takings_paise"] for f in body["films"]) == body["takings_paise"]
    assert sum(f["seats_sold"] for f in body["films"]) == body["seats_sold"]
    assert after["takings_paise"] == 2808331


def test_a_failing_per_film_query_returns_no_figure_at_all(world, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("injected per-film failure")

    monkeypatch.setattr(rpt, "films", broken)
    with make_client(world["db"]) as c:
        r = get(c, world["M"], DAY)
        four = [get(c, world["M"], "/api/reports/dashboard?period=year"), get(c, world["M"], DAY + "&screen_id=1"),
                get(c, None, DAY), get(c, world["customer"], DAY)]
    assert r.status_code == 500 and "takings_paise" not in r.json() and "takings_paise" not in r.text
    rid = r.json()["error"]["request_id"]
    assert re.fullmatch(r"[0-9a-f]{8}", rid)
    assert r.json()["error"]["message"] == f"This period's figures could not be loaded. If you need help, quote {rid}."
    assert r.json()["error"]["message"].endswith(f"quote {rid}.")
    assert [x.status_code for x in four] == [422, 403, 401, 403]
    assert all("quote " not in x.text for x in four)

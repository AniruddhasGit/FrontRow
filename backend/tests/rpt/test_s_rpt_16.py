"""S-RPT-16 - every figure computed live from stored rows, with the required indexes and no rollup (P-RPT-12)."""

from __future__ import annotations

import pytest

from tests.rpt.kit import DAY, client, get, one, owner_sql, prd_world, redis_sync, sell  # noqa: F401
from tests.xct._support import rg


@pytest.fixture(scope="module")
def world(migrated_db):
    return prd_world(migrated_db)


def test_no_rollup_anywhere(world):
    assert rg(r"MATERIALIZED VIEW|rollup|report_cache", "backend/migrations", "backend/app") == []
    assert one(world["db"], "SELECT count(*) FROM pg_matviews") == 0


def test_the_only_key_a_dashboard_request_creates_is_the_callers_bucket(client, world):
    r = redis_sync()
    try:
        before = set(r.scan_iter("*"))
        first = get(client, world["M"], DAY).json()["takings_paise"]
        created = set(r.scan_iter("*")) - before
        assert created == {f"rl:reports:user:{world['M']}".encode()}
        assert not [k for k in r.scan_iter("*") if r.type(k) == b"string" and b"takings_paise" in (r.get(k) or b"")]
        assert not [k for k in r.scan_iter("*") if r.type(k) == b"hash" and any(b"takings_paise" in v for v in r.hvals(k))]
    finally:
        r.close()
    sell(world, 101, 1, 25000)
    assert get(client, world["M"], DAY).json()["takings_paise"] == first + 25000


def test_the_required_indexes_exist(world):
    defs = [r[0] for r in owner_sql(world["db"], "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public'")]
    for table, cols in (("showtime", "(starts_at)"), ("showtime", "(screen_id, starts_at)"), ("booking", "(showtime_id)"),
                        ("booking_seat", "(booking_id)"), ("booking", "(payment_id)"), ("payment", "(state)")):
        assert [d for d in defs if f"ON public.{table} USING btree {cols}" in d], (table, cols)


def test_the_payment_join_runs_from_booking_and_the_column_does_not_exist(world):
    assert rg(r"payment\.booking_id", "backend/app", "backend/migrations") == []
    assert one(world["db"], "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                            "AND table_name='payment' AND column_name='booking_id'") == 0


def test_no_metrics_source_and_no_reporting_inside_the_booking_transaction():
    assert rg(r"metrics", "backend/app/api/reports", "backend/app/domain/reports") == []
    assert rg(r"app\.domain\.reports|app\.api\.reports", "backend/app/domain/booking") == []

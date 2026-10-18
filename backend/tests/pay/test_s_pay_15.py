"""S-PAY-15 (P-PAY-07, P-PAY-09): drive the deliberate payment failure by hand - fail, retry, succeed - with no double charge."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.pay.kit import FIVE, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
FAILING = "FAIL_9f2c1d4e-7b83-4a16-9c05-2e6f8a31b7d0"
FRONTEND = Path("/frontend/src")


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_fail_retry_succeed_in_three_requests(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        one = await confirm(c, u, h["hold_token"], key=FAILING)
        assert one.status_code == 402 and one.json()["error"]["code"] == "PAYMENT_FAILED"
        assert one.json()["error"]["message"] == (
            "The payment did not go through and you have not been charged. You can try again while the countdown is still running. "
            "If it has reached zero your hold has ended and you will need to choose your seats again.")
        assert owner_sql(db, "SELECT state FROM payment WHERE idempotency_key = %s", (FAILING,)) == [("failed",)]
        assert count(db, "SELECT count(*) FROM booking") == 0
        assert count(db, "SELECT count(*) FROM idempotency_record WHERE idempotency_key = %s", (FAILING,)) == 0
        two = await confirm(c, u, h["hold_token"], key=FAILING)
        assert two.status_code == 402
        assert count(db, "SELECT count(*) FROM booking") == 0
        assert count(db, "SELECT count(*) FROM payment WHERE state='failed'") == 2
        three = await confirm(c, u, h["hold_token"], key="2b8e4f10-6a3c-4d27-8e91-5f0a7c3d2e18")  # the same live hold
        assert three.status_code == 201, three.text
    assert count(db, "SELECT count(*) FROM booking WHERE showtime_id=7 AND user_id=%s", (u,)) == 1
    assert count(db, "SELECT count(*) FROM payment WHERE state='captured'") == 1


def test_no_control_in_the_product_sets_the_failing_header():
    hits = [str(p) for p in FRONTEND.rglob("*") if p.is_file() and p.suffix in (".ts", ".tsx", ".mjs", ".css", ".html")
            and re.search(r"FAIL_|PAYMENT_SIMULATOR_FAIL", p.read_text(encoding="utf-8"))]
    assert hits == []

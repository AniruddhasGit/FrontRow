"""S-TKT-11 (P-TKT-02 row 6, P-TKT-07 rows 5-5a, S7.4): the reference lookup and the resend are rate limited.

Every advance is the injected clock's: the limiter passes the application's instant into its Lua script and never asks
Redis the time (app/core/ratelimit.py), so real Redis honours injected advances without a test double.

NOT asserted (the row stays Blocked on them):
- "the PostgreSQL query counter for the request is 0" with Redis unreachable. On EP-TKT-01 the router's one dependency
  reads the caller's users row (role and password_version from the row, P-ACC-05) before the limiter runs; on EP-TKT-02
  the per-booking interval is spent only on acceptance (S-TKT-10), which needs the dispatch row read first. Both are
  503 with no fallback - asserted below - but neither can be 0 queries without moving authorisation or acceptance after
  the limiter. A design conflict filed as a doc defect.
- the SCR-TKT-01 render clauses (Retry-After: 7 -> 'in 7 seconds', the rg over frontend/src): frontend/src/features/
  ticket is another lane's, and the rg currently hits frontend/src/features/reports/reports.test.mjs:227.
"""

from __future__ import annotations

import socket

import pytest

from tests.dbkit import FAKE_HASH
from tests.pay.kit import api, clock_at, cookies, flush
from tests.tkt.kit import booking, owner_sql, set_claim, truncate

pytestmark = pytest.mark.anyio
REF = "/api/bookings/by-reference/FR-ACDE-FHJD"


@pytest.fixture
def world(migrated_db):
    truncate(migrated_db)
    flush()
    b = booking(migrated_db)
    owner = owner_sql(migrated_db, "SELECT user_id FROM booking WHERE id = %s", (b,))[0][0]
    return migrated_db, b, owner


async def test_the_21st_lookup_in_one_minute_is_429_retry_after_3(world):
    db, _, owner = world
    async with api(db, clock_at(), RATE_LIMIT_LOOKUP_USER_PER_MIN="20") as c:
        rs = [await c.get(REF, cookies=cookies(c, owner)) for _ in range(21)]
    assert [r.status_code for r in rs[:20]] == [200] * 20
    r = rs[20]
    assert (r.status_code, r.headers["retry-after"]) == (429, "3")
    assert r.json()["error"]["message"] == "Too many attempts. Try again in 3 seconds."


async def test_the_61st_lookup_from_one_address_across_accounts_is_retry_after_1_singular(world):
    db, _, owner = world
    others = [owner_sql(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, 'customer', 1) "
                            "RETURNING id", (f"other{i}@example.invalid", FAKE_HASH))[0][0] for i in range(3)]
    async with api(db, clock_at(), RATE_LIMIT_LOOKUP_IP_PER_MIN="60") as c:
        # 4 accounts x 15 = 60, and 15 keeps every per-user bucket (20) open: only the address's bucket can refuse. A
        # non-owner's lookup is 404, but it spends its tokens first like any other (EP-TKT-01: counted before the read).
        rs = [await c.get(REF, cookies=cookies(c, u)) for u in [owner, *others] for _ in range(15)]
        r = await c.get(REF, cookies=cookies(c, others[0]))
    assert [x.status_code for x in rs].count(429) == 0 and len(rs) == 60
    assert (r.status_code, r.headers["retry-after"]) == (429, "1")
    assert r.json()["error"]["message"] == "Too many attempts. Try again in 1 second."


async def test_a_resend_inside_the_interval_reads_240_then_50_rendered_as_minutes_then_seconds(world):
    db, b, owner = world
    set_claim(db, b, "sent")
    clock = clock_at()
    async with api(db, clock, RECEIPT_RESEND_MIN_INTERVAL_SECONDS="300") as c:
        first = await c.post(f"{REF}/resend-receipt", cookies=cookies(c, owner))
        set_claim(db, b, "sent", seq=2)  # the worker sent it: a second resend has something to send
        clock.advance(60)
        at_60 = await c.post(f"{REF}/resend-receipt", cookies=cookies(c, owner))
        clock.advance(190)
        at_250 = await c.post(f"{REF}/resend-receipt", cookies=cookies(c, owner))
    assert first.status_code == 202 and first.json()["queued"] is True
    assert (at_60.status_code, at_60.headers["retry-after"]) == (429, "240")
    assert at_60.json()["error"]["message"] == "A receipt was requested recently. You can request another in 4 minutes."
    assert (at_250.status_code, at_250.headers["retry-after"]) == (429, "50")
    assert at_250.json()["error"]["message"] == "A receipt was requested recently. You can request another in 50 seconds."


async def test_redis_unreachable_is_503_on_both_endpoints(world):
    db, b, owner = world
    set_claim(db, b, "sent")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    async with api(db, clock_at(), REDIS_URL=f"redis://127.0.0.1:{port}/11") as c:
        lookup = await c.get(REF, cookies=cookies(c, owner))
        resend = await c.post(f"{REF}/resend-receipt", cookies=cookies(c, owner))
    assert (lookup.status_code, lookup.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert (resend.status_code, resend.json()["error"]["code"]) == (503, "DEPENDENCY_UNAVAILABLE")
    assert owner_sql(db, "SELECT count(*) FROM outbox_message")[0][0] == 0  # no fallback enqueued anything

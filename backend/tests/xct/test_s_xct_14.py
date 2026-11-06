"""S-XCT-14 (P-XCT-07, S7.4): two buckets per limited request in one Lua call, both must pay, failing closed.

On the booking lane's kit (tests/pay/kit.py: Redis db 11, injected clock, the app's Redis client wrapped). Showtime 41
is added to its world with seats 310..315, so the criterion's own ids are used: seat 312 on showtime 41.

NOT asserted here, and why (the row stays Blocked on it): `rg -nP '(?<![\\w.])[2-9]\\d*(?![\\w.])'` over
app/core/ratelimit.py returning 0 hits. The pattern matches every number from 2 up - the 900/3600/60-second WINDOWS of
S7.4's table, the 60 in S7.20's seconds-to-minutes rule and the Lua script's argument stride - none of which is a bucket
SIZE. Bucket sizes are named settings (asserted below by the RATE_LIMIT_ census). Rewriting those numbers so the regex
finds nothing would be grep-gaming; it is filed as an AC defect instead.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import VALID_ENV
from tests.pay import kit
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio

SHOWTIME, SEAT = 41, 312
UNAVAILABLE = "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes."
BACKEND_DIR = Path(__file__).resolve().parents[2]


def world41(db) -> dict:
    w = kit.world7(db)
    for n in range(310, 316):
        kit._seat(db, w["screen"], n, "D", n - 300, 4, w["standard"])
    kit.showtime(db, w["movie"], w["screen"], SHOWTIME)
    return w


async def _hold(c, user: int, seat: int = SEAT, **kw):
    return await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [seat]}, cookies=kit.cookies(c, user), **kw)


async def test_the_user_bucket_refuses_one_customer_while_another_from_the_same_address_is_admitted(migrated_db):
    world41(migrated_db)
    a, b = kit.user(migrated_db), kit.user(migrated_db)
    async with kit.api(migrated_db, kit.clock_at(), RATE_LIMIT_HOLD_USER_PER_MIN="1", RATE_LIMIT_HOLD_IP_PER_MIN="100") as c:
        first = await _hold(c, a, 310)
        second = await _hold(c, a, 311)
        other = await _hold(c, b, SEAT)
    assert (first.status_code, second.status_code, other.status_code) == (201, 429, 201)


async def test_the_ip_bucket_refuses_the_second_customer_from_one_address(migrated_db):
    world41(migrated_db)
    a, b = kit.user(migrated_db), kit.user(migrated_db)
    async with kit.api(migrated_db, kit.clock_at(), RATE_LIMIT_HOLD_USER_PER_MIN="100", RATE_LIMIT_HOLD_IP_PER_MIN="1") as c:
        first = await _hold(c, a, 310)
        second = await _hold(c, b, SEAT)
        # One Lua invocation per limited request, evaluating both keys.
        evals = [cmd for cmd in c.redis_log.commands if cmd[0].upper() == "EVAL" and cmd[3].startswith("rl:")]
    assert (first.status_code, second.status_code) == (201, 429)
    # One limiter EVAL per request, carrying BOTH keys: EVAL <script> 2 rl:hold:user:<id> rl:hold:ip:<addr> ...
    assert len(evals) == 2 and all(e[2] == "2" and e[3].startswith("rl:hold:user:") and e[4].startswith("rl:hold:ip:") for e in evals)


async def test_an_empty_bucket_is_429_with_integer_retry_after_equal_to_the_detail(migrated_db):
    world41(migrated_db)
    a = kit.user(migrated_db)
    async with kit.api(migrated_db, kit.clock_at(), RATE_LIMIT_HOLD_USER_PER_MIN="1") as c:
        await _hold(c, a, 310)
        r = await _hold(c, a, 311)
    error = r.json()["error"]
    assert (r.status_code, error["code"]) == (429, "RATE_LIMITED")
    assert re.fullmatch(r"[0-9]+", r.headers["retry-after"])
    assert error["details"]["retry_after_seconds"] == int(r.headers["retry-after"])


async def test_redis_unreachable_is_503_with_the_hold_sentence_after_exactly_one_redis_command(migrated_db):
    world41(migrated_db)
    a = kit.user(migrated_db)
    with socket.socket() as s:  # a port nothing listens on: "Redis stopped" for this app
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    async with kit.api(migrated_db, kit.clock_at(), REDIS_URL=f"redis://127.0.0.1:{port}/11") as c:
        c.redis_log.reset()
        r = await _hold(c, a)
        sent = list(c.redis_log.commands)
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE)
    assert [cmd[0] for cmd in sent] == ["EVAL"]


async def test_a_repeated_idempotency_key_still_spends_a_token(migrated_db):
    world41(migrated_db)
    a = kit.user(migrated_db)
    async with kit.api(migrated_db, kit.clock_at(), RATE_LIMIT_CONFIRM_USER_PER_MIN="2") as c:
        held = await _hold(c, a)
        token = held.json()["hold_token"]
        rs = [await kit.confirm(c, a, token, showtime_id=SHOWTIME) for _ in range(3)]
    assert [r.status_code for r in rs] == [201, 201, 429]
    assert rs[0].content == rs[1].content  # the repeat was the replay of an already-seen key, not a new booking
    assert rs[2].json()["error"]["code"] == "RATE_LIMITED"


def test_every_bucket_size_is_one_named_rate_limit_declaration():
    # S7.4's table: hold 2, confirm 2, login 2, register 1, reset request 1, reset confirm 1, lookup 2, seat map 1,
    # reports 1 = 13 buckets (the resend's per-booking row is an interval, RECEIPT_RESEND_MIN_INTERVAL_SECONDS).
    lines = [ln for ln in (REPO / "backend/app/core/config.py").read_text(encoding="utf-8").splitlines() if "RATE_LIMIT_" in ln]
    assert len(lines) == 13, lines
    assert all(re.match(r"\s+[A-Z_]*RATE_LIMIT_[A-Z0-9_]+: int = Field\(", ln) for ln in lines), lines


def test_a_wildcard_forwarded_allow_ips_refuses_to_boot_naming_the_variable(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({**VALID_ENV, "FORWARDED_ALLOW_IPS": "*", "PYTHONPATH": str(BACKEND_DIR)})
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "FORWARDED_ALLOW_IPS" in proc.stderr

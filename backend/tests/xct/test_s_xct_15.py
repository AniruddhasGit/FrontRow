"""S-XCT-15 (P-XCT-07, S7.4): the limiter keys on the address the load balancer reports, never on the load balancer.

The "local proxy" is the ASGI transport's peer address: every request arrives FROM 10.0.0.2 (the ALB, named by
FORWARDED_ALLOW_IPS) carrying X-Forwarded-For exactly as an ALB writes it - whatever the client sent, then the peer it
saw, 198.51.100.77, appended on the right. Against a limiter that trusted the leftmost entry the third request is 201.

NOT asserted here (the row stays Blocked on them): `rg 'proxy-headers'` / `rg 'forwarded-allow-ips'` over the
entrypoint returning one hit each - the design runs uvicorn with proxy_headers=False and reads X-Forwarded-For itself
(app/server.py, app/core/ratelimit.py client_ip), so neither flag exists to find; and the body field `bucket` - the
hold body forbids unknown properties, so that request is 422 before the limiter, which selects nothing either.
"""

from __future__ import annotations

import re

import pytest

from tests.dbkit import FAKE_HASH, owner_sql
from tests.pay import kit
from tests.xct.test_s_xct_14 import SHOWTIME, world41

pytestmark = pytest.mark.anyio

ALB, CLIENT = "10.0.0.2", "198.51.100.77"
KEY_SHAPE = re.compile(r"^rl:[a-z][a-z_]*:(user|ip):[0-9a-zA-Z.:_-]+$")


def _customer(db, user_id: int) -> int:
    return owner_sql(db, "INSERT INTO users (id, email, password_hash, role, password_version) OVERRIDING SYSTEM VALUE "
                         "VALUES (%s, %s, %s, 'customer', 1) RETURNING id", (user_id, f"u{user_id}@example.invalid", FAKE_HASH))[0][0]


def _alb(sent: str | None) -> dict[str, str]:
    """What the ALB forwards: the client's own header (if any), then the peer address appended."""
    return {"X-Forwarded-For": f"{sent}, {CLIENT}" if sent else CLIENT}


async def test_two_forged_leftmost_values_change_nothing_and_all_three_share_one_bucket(migrated_db, log_capture):
    world41(migrated_db)
    user = _customer(migrated_db, 4471)
    async with kit.api(migrated_db, kit.clock_at(), client_addr=(ALB, 40000), FORWARDED_ALLOW_IPS=ALB,
                       RATE_LIMIT_HOLD_IP_PER_MIN="2") as c:
        rs = []
        for seat, sent in ((310, "203.0.113.9"), (311, "192.0.2.5"), (312, None)):
            rs.append(await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [seat]}, headers=_alb(sent),
                                   cookies=kit.cookies(c, user)))
    assert [r.status_code for r in rs] == [201, 201, 429]
    assert rs[2].headers["retry-after"] == "30"
    assert rs[2].json()["error"]["message"] == "Too many attempts. Try again in 30 seconds."
    done = [ln for ln in log_capture.lines() if ln["message"] == "request completed" and ln.get("route", "").endswith("/holds")]
    assert [ln["client_ip"] for ln in done] == [CLIENT] * 3


async def test_nothing_client_supplied_selects_the_key_and_the_two_keys_are_literal(migrated_db):
    world41(migrated_db)
    user = _customer(migrated_db, 4471)
    async with kit.api(migrated_db, kit.clock_at(), client_addr=(ALB, 40000), FORWARDED_ALLOW_IPS=ALB,
                       RATE_LIMIT_HOLD_IP_PER_MIN="1") as c:
        first = await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [310]}, headers=_alb(None),
                             cookies=kit.cookies(c, user))
        c.redis_log.reset()
        second = await c.post(f"/api/showtimes/{SHOWTIME}/holds?bucket=other", json={"seat_ids": [311]},
                              headers={**_alb(None), "X-RateLimit-Key": "other"}, cookies=kit.cookies(c, user))
        [limiter] = [cmd for cmd in c.redis_log.commands if cmd[0].upper() == "EVAL"]
    assert (first.status_code, second.status_code) == (201, 429)
    keys = list(limiter[3:3 + int(limiter[2])])
    assert keys == ["rl:hold:user:4471", f"rl:hold:ip:{CLIENT}"]
    assert all(KEY_SHAPE.match(k) for k in keys)

"""S-SEA-14 (P-HLD-09), the server half: the hold carries an absolute UTC instant, never a duration.

The countdown's arithmetic (1:15, 1:00 with the warning, 0:00 and never negative, the in-flight wording) is
unit-tested in frontend/src/features/seatmap/hold.test.mjs. Not here (browser harness): the rendered DOM - the
required `now` prop raising, the fake timer, the live region, the colour tokens, sessionStorage versus
localStorage, the reload, and the unload spy.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.sea.kit import SHOWTIME, T0, SetClock, api, session, user, world77
from tests.xct._support import REPO

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(migrated_db):
    return world77(migrated_db)


async def test_the_hold_carries_expires_at_with_milliseconds_and_no_duration(world):
    contract = json.loads((REPO / "docs/03 PRD/api/contract.json").read_text(encoding="utf-8"))
    declared = set(next(e for e in contract["endpoints"] if e["id"] == "EP-HLD-01")["responses"]["201"]["body"])
    clock = SetClock()
    clock.set(T0)
    customer = user(world["db"])
    async with api(world["db"], clock) as c:
        cookies = session(c, customer)
        hold = (await c.post(f"/api/showtimes/{SHOWTIME}/holds", json={"seat_ids": [402]}, cookies=cookies)).json()
        read = (await c.get(f"/api/holds/{hold['hold_token']}", cookies=cookies)).json()
    assert set(hold) == declared == {"hold_token", "showtime_id", "expires_at", "seats", "total_paise"}
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", hold["expires_at"])
    assert not [k for k in hold if re.search(r"duration|remaining|seconds|ttl", k)]
    assert read["expires_at"] == hold["expires_at"]

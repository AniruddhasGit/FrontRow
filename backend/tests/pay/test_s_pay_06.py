"""S-PAY-06 (P-PAY-09): the idempotency record is inserted first, and a duplicate is answered in exactly three ways."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from tests.pay.kit import FIVE, F7, J3, KEY, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def test_a_missing_empty_or_overlong_key_is_400_and_writes_nothing(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        c.statements.reset()
        r = await confirm(c, u, h["hold_token"], key=None)
        assert r.status_code == 400 and r.json()["error"]["code"] == "REQUEST_INVALID"
        # The only statements are the session's own user read and its rollback: no BEGIN of a booking transaction.
        assert not [s for s in c.statements.statements if "idempotency_record" in s or "payment" in s]
        for bad in ("", "k" * 256):
            r = await confirm(c, u, h["hold_token"], key=bad)
            assert r.status_code == 400 and r.json()["error"]["code"] == "REQUEST_INVALID", (len(bad), r.text)
        ok = await confirm(c, u, h["hold_token"], key="k" * 255)
        assert ok.status_code == 201, ok.text
    assert count(db, "SELECT count(*) FROM idempotency_record WHERE idempotency_key <> %s", ("k" * 255,)) == 0


async def test_the_key_is_compared_as_exact_bytes(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        for key in ("Key-Abc", "Key-Abc ", "KEY-ABC"):
            h = await hold(c, u, [F7])
            r = await confirm(c, u, h["hold_token"], key=key)
            assert r.status_code == 201, (key, r.text)
            owner_sql(db, "TRUNCATE booking_seat, receipt_dispatch, outbox_message RESTART IDENTITY")  # free the seat again
            owner_sql(db, "UPDATE idempotency_record SET booking_id = NULL")
            owner_sql(db, "DELETE FROM booking")
    assert count(db, "SELECT count(*) FROM idempotency_record WHERE user_id = %s", (u,)) == 3
    banned = r"strip\(\)|lower\(\)|upper\(\)|casefold|unicodedata"
    assert not re.search(banned, (BACKEND / "app" / "api" / "bookings.py").read_text(encoding="utf-8"))


async def test_a_completed_duplicate_replays_the_stored_body_byte_for_byte(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        first = await confirm(c, u, h["hold_token"])
        second = await confirm(c, u, h["hold_token"])
    assert first.status_code == second.status_code == 201
    assert count(db, "SELECT count(*) FROM booking WHERE user_id = %s AND showtime_id = 7", (u,)) == 1
    assert count(db, "SELECT count(*) FROM payment") == 1
    stored = owner_sql(db, "SELECT response_body::text FROM idempotency_record WHERE idempotency_key = %s", (KEY,))[0][0]
    import json

    assert json.loads(second.content) == json.loads(stored)
    assert second.content == first.content  # the replay is the original, byte for byte


async def test_a_duplicate_while_the_first_is_capturing_is_409_and_never_waits(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        gate, entered = c.sleep.hold()
        first = asyncio.create_task(confirm(c, u, h["hold_token"]))
        await asyncio.wait_for(entered.wait(), 5)
        second = await asyncio.wait_for(confirm(c, u, h["hold_token"]), 5)  # answered while the first still waits
        assert not first.done()
        assert second.status_code == 409 and second.json()["error"]["code"] == "IDEMPOTENCY_IN_FLIGHT"
        assert second.headers["Retry-After"] == "3"
        assert second.json()["error"]["message"] == "This booking is still being processed."
        gate.set()
        done = await first
    assert done.status_code == 201
    assert count(db, "SELECT count(*) FROM booking") == 1 and count(db, "SELECT count(*) FROM payment") == 1


async def test_the_same_key_with_another_hold_is_422_every_time(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        assert (await confirm(c, u, h["hold_token"])).status_code == 201
        other = await hold(c, u, [J3])
        for _ in range(2):
            r = await confirm(c, u, other["hold_token"])
            assert r.status_code == 422 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED", r.text
            assert r.json()["error"]["message"] == "This checkout is out of date. Return to the seat map and choose your seats again."


async def test_the_same_key_from_another_user_confirms_normally(world):
    db = world["db"]
    a, b = user(db), user(db)
    async with api(db, clock_at()) as c:
        ha = await hold(c, a, [F7])
        hb = await hold(c, b, [J3])
        assert (await confirm(c, a, ha["hold_token"])).status_code == 201
        assert (await confirm(c, b, hb["hold_token"])).status_code == 201
    assert count(db, "SELECT count(*) FROM idempotency_record WHERE idempotency_key = %s", (KEY,)) == 2


async def test_a_key_whose_transaction_rolled_back_inserts_cleanly_next_time(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        failing = "FAIL_retry-me"
        assert (await confirm(c, u, h["hold_token"], key=failing)).status_code == 402
        assert count(db, "SELECT count(*) FROM idempotency_record WHERE idempotency_key = %s", (failing,)) == 0
        # The same key again rolls back again (the trigger reads the key) - and inserts cleanly each time.
        assert (await confirm(c, u, h["hold_token"], key=failing)).status_code == 402


def test_nothing_ever_deletes_or_ages_out_an_idempotency_record():
    pattern = re.compile(r"DELETE FROM idempotency|idempotency.*(expire|ttl|purge)", re.IGNORECASE)
    hits = [f"{p}:{n}" for d in ("app", "migrations") for p in (BACKEND / d).rglob("*.py")
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert hits == []

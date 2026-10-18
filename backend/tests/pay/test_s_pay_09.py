"""S-PAY-09 (P-PAY-11): a unique-constraint violation at the booking_seat insert is the guard working.

Two live holders of one seat, as P-PAY-07's worked example produces them: A's hold is validated at step 2 and A
enters the capture; A's lock then ends (here: deleted, as a TTL would) and B takes the seat and confirms. A holds the
showtime row lock, so B waits at step 3; A commits, and B's single insert meets the constraint."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import psycopg
import pytest

from tests.pay.kit import F7, F8, F9, J3, api, clock_at, confirm, count, hold, owner_sql, r_call, user, world7

pytestmark = pytest.mark.anyio
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


async def _race(c, db, a_seats: list[int], b_seats: list[int]):
    a, b = user(db), user(db)
    ha = await hold(c, a, a_seats)
    gate, entered = c.sleep.hold()
    first = asyncio.create_task(confirm(c, a, ha["hold_token"], key="key-a"))
    await asyncio.wait_for(entered.wait(), 5)
    for sid in a_seats:
        r_call("DEL", f"lock:seat:7:{sid}")  # A's hold has ended while A is paying
    hb = await hold(c, b, b_seats)
    c.statements.reset()
    second = asyncio.create_task(confirm(c, b, hb["hold_token"], key="key-b"))
    await asyncio.sleep(0.2)
    assert not second.done()  # B waits on A's showtime row lock
    gate.set()
    return await first, await second, hb


async def test_two_live_holders_one_wins_and_the_loser_rolls_back_in_full(world, log_capture):
    db = world["db"]
    async with api(db, clock_at()) as c:
        won, lost, hb = await _race(c, db, [F7], [F7])
    assert won.status_code == 201, won.text
    assert lost.status_code == 409, lost.text
    err = lost.json()["error"]
    assert err["code"] == "SEAT_UNAVAILABLE" and err["details"]["unavailable_seats"] == ["F7"]
    assert err["message"] == ("F7 was taken by another customer before your payment finished. "
                              "Your booking was not made and you have not been charged.")
    assert count(db, "SELECT count(*) FROM booking_seat WHERE showtime_id=7 AND seat_id=402") == 1
    assert count(db, "SELECT count(*) FROM payment WHERE state='captured'") == 1
    assert count(db, "SELECT count(*) FROM booking") == 1
    assert count(db, "SELECT count(*) FROM booking_seat WHERE showtime_id=7") == 1
    # Logged as an expected outcome, never as an error and never as a 500.
    rid = err["request_id"]
    mine = [ln for ln in log_capture.lines() if ln.get("request_id") == rid]
    assert any(ln["level"] == "INFO" and ln.get("error_code") == "SEAT_UNAVAILABLE" for ln in mine), mine
    assert not [ln for ln in mine if ln["level"] == "ERROR" or ln.get("status_code") == 500]


async def test_three_lost_seats_are_named_in_hold_order_in_one_server_sentence_and_one_insert(world):
    db = world["db"]
    async with api(db, clock_at()) as c:
        won, lost, hb = await _race(c, db, [F9, F7, F8], [F8, J3, F7, F9])
        inserts = [s for s in c.statements.statements if s.lstrip().startswith("INSERT INTO booking_seat")]
    assert won.status_code == 201 and lost.status_code == 409
    err = lost.json()["error"]
    assert err["details"]["unavailable_seats"] == ["F7", "F8", "F9"]
    assert err["message"] == ("F7, F8 and F9 were taken by another customer before your payment finished. "
                              "Your booking was not made and you have not been charged.")
    # One insert by each request in the window - the loser's ONE attempt, never a retry.
    assert len(inserts) == 2
    assert count(db, "SELECT count(*) FROM booking_seat WHERE showtime_id=7") == 3


def test_no_conflict_clause_and_no_waiver_of_the_guard():
    app = BACKEND / "app"
    files = [app / "api" / "bookings.py", *(app / "domain").rglob("*.py")]
    assert [str(p) for p in files if "ON CONFLICT" in p.read_text(encoding="utf-8")] == []
    waiver = re.compile(r"DROP INDEX|DROP CONSTRAINT|SET CONSTRAINTS|DEFERRABLE", re.IGNORECASE)
    assert [str(p) for p in app.rglob("*.py") if waiver.search(p.read_text(encoding="utf-8"))] == []


def test_the_guard_is_one_total_unique_index_on_showtime_and_seat(world):
    db = world["db"]
    n, indexdef = owner_sql(db, "SELECT count(*), max(indexdef) FROM pg_indexes WHERE tablename = 'booking_seat' AND "
                                "indexname <> 'booking_seat_pkey' AND indexdef LIKE 'CREATE UNIQUE INDEX %'")[0]
    assert n == 1 and "(showtime_id, seat_id)" in indexdef and " WHERE " not in indexdef
    with pytest.raises(psycopg.errors.InvalidTextRepresentation, match="invalid input syntax for type bigint"):
        owner_sql(db, "SELECT count(*) FROM booking_seat WHERE seat_id = 'F7'")

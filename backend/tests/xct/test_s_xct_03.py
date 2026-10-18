"""S-XCT-03 (P-XCT-01): the seat guarantee is enforced in two systems.

HERE: the total unique constraint read back from the catalogue, no ON CONFLICT anywhere, and the confirm path - no
pre-insert check, the unique violation answered 409 (rows 4 and 4b byte for byte) at INFO and never retried, READ
COMMITTED. The dropped-constraint run producing two rows is tests/xct/test_s_xct_02.py. NOT here: the
seat_conflicts_total counter (no metrics exist before Phase 7).
"""

from __future__ import annotations

from tests.dbkit import owner_sql
from tests.xct._support import rg


def test_the_constraint_is_total(migrated_db):
    rows = owner_sql(migrated_db, "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                                  "WHERE conrelid = 'booking_seat'::regclass AND contype = 'u'")
    assert rows == [("uq_booking_seat__showtime_id_seat_id", "UNIQUE (showtime_id, seat_id)")]
    assert "WHERE" not in rows[0][1]


def test_nothing_in_the_application_resolves_a_conflict_quietly():
    assert rg("ON CONFLICT", "backend/app") == []


# ---- the confirm path (EP-PAY-01) ------------------------------------------------------------------------

import logging  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from tests.pay.kit import C1, C2, api, book, clock_at, confirm, count, hold, user, world7  # noqa: E402

ONE = ("C1 was taken by another customer before your payment finished. Your booking was not made and you have not "
       "been charged.")
TWO = ("C1 and C2 were taken by another customer before your payment finished. Your booking was not made and you "
       "have not been charged.")


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


@pytest.mark.anyio
async def test_a_unique_violation_at_confirm_is_409_with_rows_4_and_4b_never_500_and_logged_at_info(world, caplog):
    db = world["db"]
    u, other = user(db), user(db)
    async with api(db, clock_at()) as c:
        lone = await hold(c, u, [C1])
        book(db, other, 7, [C1])  # committed outside the hold path: the lock was won, the constraint decides
        c.statements.reset()
        with caplog.at_level(logging.INFO, logger="app.bookings"):
            one_lost = await confirm(c, u, lone["hold_token"], key="k-one")
        sql = list(c.statements.statements)
    assert (one_lost.status_code, one_lost.json()["error"]["code"], one_lost.json()["error"]["message"]) == (
        409, "SEAT_UNAVAILABLE", ONE)
    # no pre-insert availability check: the only statement naming booking_seat before the refusal is the INSERT
    before_insert = [s for s in sql if "booking_seat" in s]
    assert before_insert and "INSERT INTO booking_seat" in before_insert[0]
    assert sum("INSERT INTO booking_seat" in s for s in sql) == 1  # tried once, never retried
    taken = [r for r in caplog.records if r.name == "app.bookings" and r.getMessage() == "seat taken at confirm"]
    assert taken and all(r.levelno == logging.INFO and not r.exc_info for r in taken)


@pytest.mark.anyio
async def test_the_two_seat_sentence_byte_for_byte(world):
    db = world["db"]
    u, other = user(db), user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1, C2])
        book(db, other, 7, [C1, C2])
        r = await confirm(c, u, h["hold_token"])
    assert (r.status_code, r.json()["error"]["message"], r.json()["error"]["details"]["unavailable_seats"]) == (
        409, TWO, ["C1", "C2"])


@pytest.mark.anyio
async def test_a_violation_whose_rows_cannot_be_read_back_is_still_409_never_500(world, monkeypatch):
    """Round 3 verifier: sold_labels returning [] made taken_message([]) raise IndexError -> 500."""
    from app.domain import booking as bk

    async def nothing(conn, showtime_id, hold):
        await conn.rollback()
        return []

    db = world["db"]
    u, other = user(db), user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1])
        book(db, other, 7, [C1])
        monkeypatch.setattr(bk, "sold_labels", nothing)
        r = await confirm(c, u, h["hold_token"])
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (409, "SEAT_UNAVAILABLE", ONE)


@pytest.mark.anyio
async def test_the_confirm_transaction_runs_at_read_committed(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        async with c.application.state.db_engine.connect() as conn, conn.begin():
            level = (await conn.execute(text("SHOW transaction_isolation"))).scalar_one()
        h = await hold(c, u, [C1])
        c.statements.reset()
        r = await confirm(c, u, h["hold_token"])
        sql = list(c.statements.statements)
    assert r.status_code == 201 and level == "read committed"
    assert not [s for s in sql if "ISOLATION" in s.upper()]  # the confirm never raises its level
    assert count(db, "SELECT count(*) FROM booking") == 1

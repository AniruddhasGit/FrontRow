"""S-TKT-01 (P-TKT-01, SRC-004 R-5): a unique booking reference is generated inside the confirm transaction."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest

from app.domain import reference as refs
from tests.pay.kit import C1, C2, F7, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
APP = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


class Draws:
    """The draw, stubbed: hands out the given references in order and counts the calls."""

    def __init__(self, values: list[str]) -> None:
        self.values, self.calls = list(values), 0

    def __call__(self) -> str:
        self.calls += 1
        return self.values.pop(0)


def _ref(payload: str) -> str:
    return payload + refs.check_character(payload)


async def test_a_stubbed_draw_is_stored_as_eight_upper_case_characters(world):
    db = world["db"]
    u = user(db)
    known = _ref("7K3MQP4")
    async with api(db, clock_at()) as c:
        c.application.state.draw_reference = Draws([known])
        h = await hold(c, u, [F7])
        r = await confirm(c, u, h["hold_token"])
    assert r.status_code == 201 and r.json()["booking_reference"] == f"FR-{known[:4]}-{known[4:]}"
    assert owner_sql(db, "SELECT length(reference), reference = upper(reference), reference FROM booking WHERE id = %s",
                     (r.json()["booking_id"],)) == [(8, True, known)]


def test_a_thousand_references_fit_the_alphabet_and_carry_their_check_character(world):
    db = world["db"]
    u = user(db)
    drawn = list({refs.new_reference() for _ in range(1000)})
    with psycopg.connect(db.owner_url) as conn, conn.transaction():
        pay = conn.execute("INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at) "
                           "VALUES ('captured', 1, 'bulk', '2026-08-14T14:00:00Z', '2026-08-14T14:00:01Z', '2026-08-14T14:00:02Z') "
                           "RETURNING id").fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) "
                            "VALUES (%s, %s, 7, %s, 1, 'confirmed')", [(r, u, pay) for r in drawn])
    assert count(db, "SELECT count(*) FROM booking") == len(drawn) == 1000
    assert count(db, "SELECT count(*) FROM booking WHERE reference !~ '^[23456789ACDEFHJKMNPQRTVWXY]{8}$'") == 0
    drawn = [row[0] for row in owner_sql(db, "SELECT reference FROM booking")]
    for ref in drawn:
        assert re.fullmatch(r"[23456789ACDEFHJKMNPQRTVWXY]{8}", ref), ref
        assert ref[7] == refs.check_character(ref[:7])
        assert not set(ref) & set("01BGILOSUZ") and not ref.startswith("FR-") and "-" not in ref


def test_the_unique_constraint_refuses_a_second_copy(world):
    db = world["db"]
    u = user(db)
    from tests.brw.kit import book_seat

    booking = book_seat(db, 7, C1)
    stored = owner_sql(db, "SELECT reference FROM booking WHERE id = %s", (booking,))[0][0]
    with pytest.raises(psycopg.errors.UniqueViolation):
        owner_sql(db, "INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) "
                      "SELECT reference, %s, showtime_id, payment_id, total_paise, status FROM booking WHERE id = %s", (u, booking))
    assert count(db, "SELECT count(*) FROM booking WHERE reference = %s", (stored,)) == 1


async def test_four_collisions_then_a_free_value_books(world):
    db = world["db"]
    u = user(db)
    from tests.brw.kit import book_seat

    taken = owner_sql(db, "SELECT reference FROM booking WHERE id = %s", (book_seat(db, 7, C2),))[0][0]
    free = _ref("ACDEFHJ")
    draws = Draws([taken] * 4 + [free])
    async with api(db, clock_at()) as c:
        c.application.state.draw_reference = draws
        h = await hold(c, u, [F7])
        r = await confirm(c, u, h["hold_token"])
    assert r.status_code == 201, r.text
    assert draws.calls == 5
    assert count(db, "SELECT count(*) FROM booking WHERE reference = %s", (free,)) == 1


async def test_five_collisions_is_500_and_sells_nothing(world):
    db = world["db"]
    u = user(db)
    from tests.brw.kit import book_seat

    taken = owner_sql(db, "SELECT reference FROM booking WHERE id = %s", (book_seat(db, 7, C2),))[0][0]
    draws = Draws([taken] * 6)
    async with api(db, clock_at()) as c:
        c.application.state.draw_reference = draws
        h = await hold(c, u, [F7])
        r = await confirm(c, u, h["hold_token"])
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert draws.calls == 5
    assert count(db, "SELECT count(*) FROM booking WHERE user_id = %s", (u,)) == 0
    assert count(db, "SELECT count(*) FROM booking_seat WHERE showtime_id = 7 AND seat_id = %s", (F7,)) == 0


def test_the_source_is_secrets_and_never_random():
    sources = {str(p): p.read_text(encoding="utf-8") for p in APP.rglob("*.py")}
    assert any("import secrets" in s for s in sources.values())
    assert [p for p, s in sources.items() if re.search(r"random\.", s)] == []

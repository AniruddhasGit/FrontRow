"""S-TKT-02 (P-TKT-02, EP-TKT-01): a typed reference is normalised and nothing is corrected; the endpoint is no
enumeration oracle."""

from __future__ import annotations

import re

import pytest

from tests.brw.kit import without_request_id
from tests.pay.kit import api, clock_at, cookies, flush
from tests.tkt.kit import booking, owner_sql, truncate

pytestmark = pytest.mark.anyio
URL = "/api/bookings/by-reference/"


@pytest.fixture
def world(migrated_db):
    truncate(migrated_db)
    flush()
    b = booking(migrated_db)
    owner = owner_sql(migrated_db, "SELECT user_id FROM booking WHERE id = %s", (b,))[0][0]
    other = booking(migrated_db, reference="KMNPQRTV", email="other@example.com")
    other_owner = owner_sql(migrated_db, "SELECT user_id FROM booking WHERE id = %s", (other,))[0][0]
    return migrated_db, owner, other_owner


@pytest.mark.parametrize("typed", ["FR-ACDE-FHJD", "fr acde fhjd", "acdefhjd", "  FR-acde-FHJD  "])
async def test_every_typed_form_of_the_owners_reference_resolves(world, typed):
    db, owner, _ = world
    async with api(db, clock_at()) as c:
        r = await c.get(URL + typed, cookies=cookies(c, owner))
    assert r.status_code == 200, r.text
    assert r.json()["reference"] == "FR-ACDE-FHJD"


@pytest.mark.parametrize("typed", ["FR-0BCD-EFGH", "FR-1BCD-EFGH", "FR-ABCD-EFG", "АВСDEFGH"])
async def test_nothing_is_corrected_and_no_non_ascii_folds_onto_the_alphabet(world, typed):
    db, owner, _ = world
    async with api(db, clock_at()) as c:
        r = await c.get(URL + typed, cookies=cookies(c, owner))
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_a_65_character_value_is_refused_with_no_database_query(world):
    db, owner, _ = world
    async with api(db, clock_at()) as c:
        c.statements.reset()
        r = await c.get(URL + "A" * 65, cookies=cookies(c, owner))
        assert r.status_code == 404 and c.statements.statements == []


async def test_the_match_is_one_equality_predicate(world):
    db, owner, _ = world
    async with api(db, clock_at()) as c:
        c.statements.reset()
        assert (await c.get(URL + "FR-ACDE-FHJD", cookies=cookies(c, owner))).status_code == 200
        log = "\n".join(c.statements.statements)
    assert "reference = " in log
    assert not re.search(r"like |similarity\(| ~\* ", log, re.IGNORECASE)


async def test_malformed_unknown_and_another_customers_reference_answer_identically(world):
    db, owner, other_owner = world
    async with api(db, clock_at()) as c:
        bodies = []
        for typed in ("FR-0BCD", "FR-CDEF-HJKJ", "FR-KMNP-QRTV"):
            r = await c.get(URL + typed, cookies=cookies(c, owner))
            bodies.append((r.status_code, without_request_id(r.json())))
    assert other_owner != owner
    assert bodies[0] == bodies[1] == bodies[2] and bodies[0][0] == 404

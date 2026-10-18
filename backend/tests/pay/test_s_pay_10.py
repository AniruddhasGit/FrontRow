"""S-PAY-10 (P-PAY-08, P-PAY-06): no card, tax, fee or discount field anywhere on the payment path.

The checkout screen's clauses are asserted in frontend/src/features/booking/checkout.test.mjs (rendered markup)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.pay.kit import FIVE, F7, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
REPO = Path("/repo")
SENTENCE = "This request could not be processed. Return to the seat map and choose your seats again."


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


def test_no_card_shaped_name_anywhere():
    """The AC's rg over backend/app, backend/migrations, frontend/src and scripts - fixtures and seeds included."""
    pattern = re.compile("|".join(["card" + "_number", "card" + "holder", "c" + "vv", "c" + "vc", "expiry" + "_month",
                                   "expiry" + "_year", "card" + "_expiry"]), re.IGNORECASE)
    roots = [REPO / "backend" / "app", REPO / "backend" / "migrations", REPO / "frontend" / "src", REPO / "scripts"]
    hits = [f"{p.relative_to(REPO)}:{n}" for root in roots for p in root.rglob("*") if p.is_file() and p.suffix in
            (".py", ".ts", ".tsx", ".mjs", ".css", ".sql", ".json", ".md", ".html")
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1) if pattern.search(line)]
    assert hits == []


# The card-instrument field name is assembled from two fragments and its value is not card-shaped: no card-shaped
# literal belongs in a fixture (P-PAY-08), and S-SCP-12's sweep keeps backend/tests in scope.
@pytest.mark.parametrize("field,value", [("card" + "_number", "zz-not-a-number"), ("discount_code", "SAVE10"), ("coupon", "HALF"),
                                         ("fee", 4500), ("tax", 1800)])
async def test_a_payment_shaped_field_is_400_and_never_echoed(world, log_capture, field, value):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        r = await confirm(c, u, h["hold_token"], body={"hold_token": h["hold_token"], "showtime_id": 7, field: value})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "REQUEST_INVALID" and r.json()["error"]["message"] == SENTENCE
    assert field not in r.text and str(value) not in r.text
    rid = r.json()["error"]["request_id"]
    raw = [ln for ln in log_capture.raw_lines() if rid in ln]
    assert raw and not [ln for ln in raw if field in ln or str(value) in ln]
    assert count(db, "SELECT count(*) FROM booking") == 0


async def test_the_charged_figures_agree_and_no_other_money_column_exists(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        r = await confirm(c, u, h["hold_token"])
    body = r.json()
    assert set(body) == {"booking_id", "booking_reference", "showtime_id", "movie_title", "screen_name", "starts_at", "seats",
                         "total_paise", "currency_code", "payment_status", "created_at"}
    b = body["booking_id"]
    assert body["total_paise"] == 166146 == 3 * 30938 + 2 * 36666
    assert owner_sql(db, "SELECT p.amount_paise, b.total_paise FROM booking b JOIN payment p ON p.id = b.payment_id WHERE b.id = %s",
                     (b,)) == [(166146, 166146)]
    assert count(db, "SELECT sum(price_paise) FROM booking_seat WHERE booking_id = %s", (b,)) == 166146
    cols = owner_sql(db, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name LIKE '%%paise%%' "
                         "AND table_name IN ('booking', 'booking_seat', 'payment')")
    assert sorted(c_[0] for c_ in cols) == ["amount_paise", "base_price_paise_applied", "price_paise", "total_paise"]

"""S-ADM-12 - a base price per showtime in integer paise (P-ADM-10).

NOT covered: the dollar form capture (no frontend test runner exists), MINOR_UNIT_RATIO/CURRENCY_CODE in
backend/app/core/money.py (the foundation put the ratio in configuration as CURRENCY_MINOR_UNIT_RATIO),
and the seat-map GET (Phase 3) - the 2812500 figure is proved through the one pricing function instead.
"""

from __future__ import annotations

import json

from app.domain.pricing import seat_price_paise
from tests.adm.kit import client, count, make_category, make_movie, make_screen, make_seats, sign_in  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import REPO, rg

TOO_LARGE = "That base price is too large for this system to hold. Enter a smaller amount."


def _post(client, hall, movie, day, **price):
    body = {"movie_id": movie, "screen_id": hall, "starts_at": f"2026-10-{day:02d} 10:00", "ends_at": f"2026-10-{day:02d} 11:00"}
    return client.post("/api/admin/showtimes", json={**body, **price})


def test_the_price_must_be_a_whole_positive_number_of_paise(client):
    sign_in(client)
    hall, movie = make_screen(client.db), make_movie(client.db)
    make_seats(client.db, hall, 1)
    before = count(client.db, "showtime")
    for price, message in ((25000.5, "Enter the base price in whole cents. A price cannot have a fraction of a cent."),
                           (0, "The base price must be at least 1 cent."), (-1, "The base price must be at least 1 cent."),
                           ("25000", "Enter the base price in whole cents. A price cannot have a fraction of a cent.")):
        r = _post(client, hall, movie, 1, base_price_paise=price)
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (422, "VALIDATION_FAILED", message)
    r = _post(client, hall, movie, 1)
    assert (r.status_code, r.json()["error"]["message"]) == (422, "Enter a base price for this showtime.")
    assert count(client.db, "showtime") == before  # never rounded, never stored
    assert _post(client, hall, movie, 2, base_price_paise=1).status_code == 201
    assert owner_sql(client.db, "SELECT data_type FROM information_schema.columns WHERE table_name = 'showtime' "
                                "AND column_name = 'base_price_paise'") == [("bigint",)]


def test_the_arithmetic_ceiling_follows_the_highest_stored_uplift(client):
    sign_in(client)
    hall, movie = make_screen(client.db), make_movie(client.db)
    make_seats(client.db, hall, 1)
    owner_sql(client.db, "UPDATE seat_category SET uplift_basis_points = 0")
    make_category(client.db, uplift=3333)
    assert _post(client, hall, movie, 3, base_price_paise=691770197019033).status_code == 201
    r = _post(client, hall, movie, 4, base_price_paise=691770197019034)
    assert (r.status_code, r.json()["error"]["message"]) == (422, TOO_LARGE)
    make_category(client.db, uplift=6666)
    r = _post(client, hall, movie, 5, base_price_paise=691770197019033)
    assert (r.status_code, r.json()["error"]["message"]) == (422, TOO_LARGE)


def test_the_bound_is_in_the_generated_contract_for_both_endpoints():
    contract = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))
    text = "base_price_paise * (10000 + highest stored uplift_basis_points) + 5000 must be <= 2^63 - 1"
    for endpoint in (e for e in contract["endpoints"] if e["id"] in ("EP-ADM-10", "EP-ADM-11")):
        assert text in json.dumps(endpoint, ensure_ascii=False)


def test_no_scattered_minor_unit_literal_in_the_application():
    assert [h for h in rg(r"[*/]\s*100\b", "backend/app") if h[0] != "backend/app/core/money.py"] == []


def test_no_business_ceiling_a_mistyped_price_is_stored_and_priced_unaltered(client):
    sign_in(client)
    hall, movie = make_screen(client.db), make_movie(client.db)
    make_seats(client.db, hall, 1)
    r = _post(client, hall, movie, 6, base_price_paise=2500000)
    assert r.status_code == 201 and r.json()["base_price_paise"] == 2500000
    assert seat_price_paise(2500000, 1250) == 2812500  # 2500000 * 11250 + 5000 = 28125005000, // 10000

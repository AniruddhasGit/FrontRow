"""S-ADM-13 - one percentage uplift per category, integer half-up (P-ADM-11, FR-ADR-038).

This module's database holds EXACTLY ONE showtime (base 25000) for the mirror-ceiling fixture; the
affected_future_showtimes fixture needs exactly four and lives in test_s_adm_13_count.py.
"""

from __future__ import annotations

from app.domain.pricing import seat_price_paise
from tests.adm.kit import audit_rows, client, count, make_category, make_movie, make_screen, make_seats, make_showtime, sign_in  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import mounted_routes, rg

CEILING = "That uplift is too large for this system to hold. Enter a smaller value."


def test_the_worked_examples_and_the_deciding_half(client):
    assert [seat_price_paise(25000, u) for u in (0, 1250, 3333)] == [25000, 28125, 33333]
    assert seat_price_paise(25000, 3333) == 33333  # exact 33332.5: half-up 33333, half-even would be 33332
    assert seat_price_paise(24999, 3333) == 33331  # 33331.1667 rounds down
    assert 3 * seat_price_paise(25000, 3333) == 99999  # per seat, the total is never rounded


def test_the_formula_file_holds_no_float_decimal_half_literal_or_standard_special_case():
    # S-ADM-13's own patterns over backend/app/domain/pricing.py (a foundation file).
    assert rg(r"float[(]|Decimal[(]|[.]5|round[(]", "backend/app/domain/pricing.py") == []
    assert rg(r"uplift_basis_points == 0|if not uplift|Standard", "backend/app/domain/pricing.py") == []
    bare = rg(r"\b(10000|5000)\b", "backend/app/domain/pricing.py")
    assert len(bare) == 2 and all("BASIS_POINT_SCALE" in line or "BASIS_POINT_HALF" in line for _, _, line in bare)


def test_create_validates_the_uplift_and_the_name(client):
    sign_in(client)
    for value, message in ((-1, "The uplift cannot be negative. This system has no discounts."),
                           (1250.5, "Enter the uplift in whole basis points. 100 basis points is 1 percent.")):
        r = client.post("/api/admin/seat-categories", json={"name": f"Bad {value}", "uplift_basis_points": value})
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (422, "VALIDATION_FAILED", message)
    r = client.post("/api/admin/seat-categories", json={"name": "Fourth Cat", "uplift_basis_points": 500})
    assert r.status_code == 201 and r.json()["version"] == 1
    r = client.post("/api/admin/seat-categories", json={"name": "  fourth cat ", "uplift_basis_points": 0})
    assert (r.status_code, r.json()["error"]["message"]) == (422, "A seat category with that name already exists.")


def test_the_mirror_ceiling_follows_the_highest_stored_base_price(client):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 1)
    st = make_showtime(client.db, hall, make_movie(client.db), "2026-09-04T13:00:00Z", "2026-09-04T15:00:00Z", price=25000)
    assert count(client.db, "showtime") == 1
    ok = client.post("/api/admin/seat-categories", json={"name": "Huge OK", "uplift_basis_points": 368934881464190})
    assert ok.status_code == 201, ok.text
    r = client.post("/api/admin/seat-categories", json={"name": "Huge NO", "uplift_basis_points": 368934881464191})
    assert (r.status_code, r.json()["error"]["message"]) == (422, CEILING)
    owner_sql(client.db, "UPDATE showtime SET base_price_paise = 50000 WHERE id = %s", (st,))
    cat = make_category(client.db, uplift=0)
    r = client.patch(f"/api/admin/seat-categories/{cat}", json={"version": 1, "uplift_basis_points": 368934881464190})
    assert (r.status_code, r.json()["error"]["message"]) == (422, CEILING)


def test_name_and_uplift_in_one_request_write_two_rows_and_there_is_no_delete(client):
    sign_in(client)
    cat = make_category(client.db, uplift=1250, name="Two Row Cat")
    r = client.patch(f"/api/admin/seat-categories/{cat}", json={"version": 1, "name": "Two Row Renamed", "uplift_basis_points": 1500})
    assert r.status_code == 200 and r.json()["version"] == 2
    rows = audit_rows(client.db, "entity_type = 'seat_category' AND entity_id = %s", (cat,))
    assert [(a, b, c) for a, _, _, b, c, _ in rows] == [
        ("seat_category.updated", {"name": "Two Row Cat"}, {"name": "Two Row Renamed"}),
        ("seat_category.uplift_changed", {"uplift_basis_points": 1250}, {"uplift_basis_points": 1500})]
    assert ("DELETE", "/api/admin/seat-categories/{seat_category_id}") not in mounted_routes(client.app)
    assert client.delete(f"/api/admin/seat-categories/{cat}").status_code == 405

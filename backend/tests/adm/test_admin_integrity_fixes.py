"""Integration fixes on the admin write path, found by the Phase 2 verifiers (not ledger rows of their own):

- the two mirror price ceilings (P-ADM-10 against the highest uplift, P-ADM-11 against the highest base price)
  read each other's table, so both must take ONE shared lock before reading, or a concurrent pair can each pass
  against the other's old value (write skew). Proved by the statement order inside each request: the advisory
  lock is taken before the other table's maximum is read.
- an integer past the column's width is a 422 (or 404), never a 500 from the driver.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.domain.admin.common import check_ceiling
from tests.adm.kit import client, make_category, make_movie, make_screen, make_seats, make_showtime, sign_in  # noqa: F401

BIGINT_MAX = 2**63 - 1


def _statements(client):
    """Record every SQL statement the app sends, in order."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.split()))

    event.listen(client.app.state.db_engine.sync_engine, "before_cursor_execute", record)
    return seen


def _lock_then_read(seen: list[str], max_of: str) -> None:
    locks = [i for i, s in enumerate(seen) if "pg_advisory_xact_lock" in s]
    reads = [i for i, s in enumerate(seen) if f"max({max_of}" in s]
    assert locks and reads, seen
    assert locks[0] < reads[0], seen


def test_a_showtime_write_takes_the_ceiling_lock_before_reading_the_highest_uplift(client):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 1)
    film = make_movie(client.db, window=("2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"))
    seen = _statements(client)
    r = client.post("/api/admin/showtimes", json={"movie_id": film, "screen_id": hall, "starts_at": "2026-11-01T18:00:00",
                                                  "ends_at": "2026-11-01T20:00:00", "base_price_paise": 25000})
    assert r.status_code == 201, r.text
    _lock_then_read(seen, "seat_category.uplift_basis_points")


def test_an_uplift_write_takes_the_same_lock_before_reading_the_highest_base_price(client):
    sign_in(client)
    seen = _statements(client)
    r = client.post("/api/admin/seat-categories", json={"name": "Lock probe", "uplift_basis_points": 1250})
    assert r.status_code == 201, r.text
    _lock_then_read(seen, "showtime.base_price_paise")


def test_the_ceiling_is_the_formulas_own_edge():
    # (25000 * (10000 + u) + 5000) <= BIGINT_MAX holds for u = 368934881464190 and fails for the next value.
    assert check_ceiling(25000, 368934881464190) is True
    assert check_ceiling(25000, 368934881464191) is False


@pytest.mark.parametrize("method,path,body", [
    ("GET", f"/api/admin/screens/{2**63}/seats", None),
    ("POST", "/api/admin/screens", {"cinema_id": 2**63, "name": "Too far"}),
    ("PATCH", f"/api/admin/showtimes/{2**63}", {"version": 1}),
])
def test_an_id_past_bigint_is_a_validation_failure_not_a_server_error(client, method, path, body):
    sign_in(client)
    r = client.request(method, path, json=body)
    assert r.status_code in (404, 422), r.text
    assert r.json()["error"]["code"] in ("NOT_FOUND", "VALIDATION_FAILED")


@pytest.mark.parametrize("field,value", [("seat_number", 2**31), ("grid_row", 2**31), ("grid_col", 2**31),
                                         ("seat_category_id", 2**63)])
def test_a_seat_integer_past_its_column_is_a_validation_failure_not_a_server_error(client, field, value):
    sign_in(client)
    hall = make_screen(client.db)
    seat = {"row_label": "A", "seat_number": 1, "grid_row": 1, "grid_col": 1, "seat_category_id": make_category(client.db)}
    r = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [{**seat, field: value}]})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_an_unknown_property_is_named_in_the_400(client):
    sign_in(client)
    r = client.post("/api/admin/screens", json={"cinema_id": 1, "name": "X", "zeta": 1, "alpha": 2})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "REQUEST_INVALID"
    assert r.json()["error"]["details"] == {"field": "alpha"}


def test_a_value_too_large_to_store_is_not_told_it_is_too_small(client):
    """Round 3 verifier: 2**40 as a seat number was answered 'Enter a seat number of 1 or more.' and 2**70 as an
    uplift 'Enter the uplift in whole basis points.' Too-large money values get the published ceiling sentence;
    a too-large seat number, for which no sentence is published, gets the registry's own words."""
    sign_in(client)
    hall = make_screen(client.db)
    seat = {"row_label": "A", "seat_number": 2**40, "grid_row": 1, "grid_col": 1, "seat_category_id": make_category(client.db)}
    big_seat = client.post(f"/api/admin/screens/{hall}/seats", json={"seats": [seat]})
    big_uplift = client.post("/api/admin/seat-categories", json={"name": "Huge", "uplift_basis_points": 2**70})
    showtime = make_showtime(client.db, hall, make_movie(client.db), "2026-09-01T12:30:00Z", "2026-09-01T15:00:00Z")
    big_price = client.patch(f"/api/admin/showtimes/{showtime}", json={"version": 1, "base_price_paise": 2**70})
    assert (big_seat.status_code, big_seat.json()["error"]["message"]) == (422, "Some fields need attention.")
    assert big_uplift.status_code == 422
    assert big_uplift.json()["error"]["message"] == "That uplift is too large for this system to hold. Enter a smaller value."
    assert big_price.status_code == 422
    assert big_price.json()["error"]["message"] == "That base price is too large for this system to hold. Enter a smaller amount."

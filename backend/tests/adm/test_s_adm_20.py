"""S-ADM-20 - ship no way to withdraw a showtime (P-ADM-21, OPEN-SHOWCANCEL-01).

NOT covered: the two published "refund" copy lines (SCR-TKT-01 and the receipt template, Phases 4/5).
The cancelled_at census is asserted for the files that exist (see the lane report on its file names).
"""

from __future__ import annotations

from tests.adm.kit import body_fields, client, count, make_movie, make_screen, make_seats, make_showtime, routes, sign_in, strip_request_id  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import rg

INVALID = "That request could not be read and nothing was changed. Reload the page and try again."
STANDING = ("Showtimes are never deleted, and v1 has no way to cancel one. Check the film, the hall and the times before "
            "you create it.")


def test_no_route_withdraws_cancels_or_carries_a_status_field(client):
    for r in routes(client.app):
        if not r.path.startswith("/api/admin"):
            continue
        assert not ("DELETE" in r.methods and "showtime" in r.path), r.path
        assert not ("POST" in r.methods and r.path.endswith(("/withdraw", "/cancel"))), r.path
        assert not ({"withdrawn", "cancelled", "status", "withdrawn_at", "cancelled_at"} & body_fields(r)), r.path


def test_a_patch_carrying_a_withdrawal_field_is_400_and_changes_nothing(client):
    sign_in(client)
    hall = make_screen(client.db)
    make_seats(client.db, hall, 1)
    st = make_showtime(client.db, hall, make_movie(client.db), "2026-09-04T13:00:00Z", "2026-09-04T15:00:00Z")
    before = owner_sql(client.db, "SELECT * FROM showtime WHERE id = %s", (st,))
    for field, value in (("withdrawn_at", "2026-09-04 10:00"), ("cancelled_at", "2026-09-04 10:00"), ("status", "cancelled")):
        r = client.patch(f"/api/admin/showtimes/{st}", json={"version": 1, field: value})
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (400, "REQUEST_INVALID", INVALID)
    assert owner_sql(client.db, "SELECT * FROM showtime WHERE id = %s", (st,)) == before


def test_the_schema_has_no_withdrawal_column_and_booking_keeps_its_affordances(client):
    assert count(client.db, "information_schema.columns", "table_schema = 'public' AND table_name = 'showtime' AND "
                                                          "column_name IN ('withdrawn_at','cancelled_at','status','is_cancelled')") == 0
    assert count(client.db, "information_schema.columns", "table_name = 'booking' AND column_name IN ('status','cancelled_at')") == 2


def test_a_withdrawal_address_is_indistinguishable_from_one_that_never_existed(client):
    sign_in(client)
    bodies = []
    for path in ("/api/admin/showtimes/601/withdraw", "/api/admin/showtimes/601/cancel", "/api/admin/no-such-address"):
        r = client.post(path, json={})
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (404, "NOT_FOUND", "That page does not exist.")
        bodies.append(strip_request_id(r.json()))
    assert bodies[0] == bodies[1] == bodies[2]


def test_scr_adm_03_carries_the_standing_text_and_no_withdraw_cancel_or_delete_control():
    assert rg(STANDING, "frontend/src/features/admin", fixed=True), "the standing text is missing"
    showtimes = "frontend/src/features/admin/ShowtimesScreen.tsx"
    assert rg(r">\s*(Withdraw|Cancel|Delete)\b|aria-label=\"(Withdraw|Cancel|Delete)", showtimes) == []


def test_cancelled_at_appears_in_no_admin_code():
    assert rg("cancelled_at", "backend/app/api", "backend/app/domain", "frontend/src") == []

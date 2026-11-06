"""S-ADM-20 - ship no way to withdraw a showtime (P-ADM-21, OPEN-SHOWCANCEL-01).

The cancelled_at census (only the booking table's model module, and the migration that creates the column) and the
`refund` sweep (only published copy) are asserted below over the application source.

NOT met, and why the row stays Blocked:
- the `refund` sweep as the cell states it also covers test files under frontend/src: frontend/src/features/ticket/
  ticket.test.mjs lines 44 and 53 quote the E6 copy in a comment and in a regex. Neither is a code path, but neither is
  a published copy line either, so the strict sweep does not return "hits only on published copy lines".
- SCR-ADM-03 RENDERING no Withdraw, Cancel or Delete control and the standing text under the day strip: checked in
  ShowtimesScreen.tsx's source below, not rendered (no render test of SCR-ADM-03 exists).
"""

from __future__ import annotations

import re

from tests.adm.kit import body_fields, client, count, make_movie, make_screen, make_seats, make_showtime, routes, sign_in, strip_request_id  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import REPO, rg

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


def test_cancelled_at_appears_only_where_the_booking_table_is_declared_and_created():
    hits = rg("cancelled_at", "backend/app", "frontend/src")
    assert {path for path, _, _ in hits} == {"backend/app/models/__init__.py"}, hits
    models = (REPO / "backend/app/models/__init__.py").read_text(encoding="utf-8")
    assert re.search(r"Table\(\s*'booking',", models)
    assert {path for path, _, _ in rg("cancelled_at", "backend/migrations")} == {"backend/migrations/versions/0001_initial_schema.py"}


PUBLISHED_REFUND_COPY = {
    "This booking cannot be changed, cancelled or refunded.",  # SCR-TKT-01
    "This booking is final. There is no cancellation and no refund.",  # the receipt template
}


def test_refund_appears_only_in_published_copy_in_the_application_source():
    """The case-insensitive `refund` sweep over backend/app, backend/migrations and frontend/src, over the application
    SOURCE files: every hit is a line carrying one of the published sentences, each E6 confirmation found word for word
    in the PRD's E6 section. Test files (*.test.mjs) are left out here - see the module docstring."""
    e6 = (REPO / "docs/03 PRD/sections/E6_admin.md").read_text(encoding="utf-8")
    hits = [h for h in rg("refund", "backend/app", "backend/migrations", "frontend/src", ignore_case=True)
            if not h[0].endswith(".test.mjs")]
    assert hits
    for path, line_no, line in hits:
        quoted = [q for q in re.findall(r'"([^"]*)"', line) if "refund" in q.lower()]
        assert len(quoted) == 1, (path, line_no, line)
        assert quoted[0] in PUBLISHED_REFUND_COPY or ("nothing is refunded" in quoted[0] and f'"{quoted[0]}"' in e6), (path, line_no)

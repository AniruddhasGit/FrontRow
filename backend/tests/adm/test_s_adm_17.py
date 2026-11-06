"""S-ADM-17 - withdraw a hall without cancelling anything (P-ADM-16).

HERE: the toggles, the refusals, the counts, GET /api/me/bookings/{reference} still rendering the hall's name and
GET /api/reports/showtimes still returning the withdrawn hall's row (both rate-limit through Redis, so that test uses
cached_client, Redis 9). NOT here: SCR-ADM-05 RENDERING the confirmation - the text is checked in the frontend source
only, and no frontend test renders the hall screen's withdrawal dialog.
"""

from __future__ import annotations

from tests.adm.kit import (audit_rows, cached_client, client, count, make_category, make_movie, make_screen, make_seat, make_showtime,  # noqa: F401
                           sign_in)
from app.domain.reference import new_reference
from tests.dbkit import insert_booking, insert_user
from tests.xct._support import mounted_routes, rg

CONFIRM = ("This hall will accept no new showtimes. Showtimes that already exist are not changed, bookings are not "
           "cancelled, and nothing is refunded. The hall is not deleted and you can bring it back into service.")


def test_withdraw_and_return_write_their_rows_and_new_showtimes_are_refused(client):
    sign_in(client)
    hall, category = make_screen(client.db), make_category(client.db)
    seat = make_seat(client.db, hall, "C12", category, grid=(3, 12))
    movie = make_movie(client.db)
    st = make_showtime(client.db, hall, movie, "2026-09-01T10:00:00Z", "2026-09-01T12:00:00Z")
    insert_booking(client.db, user_id=insert_user(client.db, role="customer"), reference="FRDEFHJK",
                   showtime={"showtime_id": st, "seat_id": seat, "seat_category_id": category}, price_paise=25000)
    counts = lambda: (count(client.db, "showtime", "screen_id = %s", (hall,)), count(client.db, "seat", "screen_id = %s", (hall,)),  # noqa: E731
                      count(client.db, "booking_seat bs JOIN showtime s ON s.id = bs.showtime_id", "s.screen_id = %s", (hall,)),
                      count(client.db, "screen"))
    before = counts()
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 1, "is_active": False})
    assert r.status_code == 200 and r.json()["version"] == 2
    assert counts() == before
    r = client.post("/api/admin/showtimes", json={"movie_id": movie, "screen_id": hall, "starts_at": "2026-09-05 10:00",
                                                   "ends_at": "2026-09-05 12:00", "base_price_paise": 25000})
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (
        409, "LAYOUT_FROZEN", "This hall is out of service. Bring it back into service before creating showtimes on it.")
    assert client.patch(f"/api/admin/screens/{hall}", json={"version": 2, "is_active": True}).status_code == 200
    assert [a[0] for a in audit_rows(client.db, "entity_type = 'screen' AND entity_id = %s", (hall,))] == [
        "screen.deactivated", "screen.reactivated"]
    audits = count(client.db, "audit_log")
    r = client.patch(f"/api/admin/screens/{hall}", json={"version": 2, "is_active": False})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "VERSION_CONFLICT")
    assert count(client.db, "audit_log") == audits
    assert ("DELETE", "/api/admin/screens/{screen_id}") not in mounted_routes(client.app)
    r = client.delete(f"/api/admin/screens/{hall}")
    assert (r.status_code, r.json()["error"]["message"]) == (405, "That action is not available. Nothing was changed.")
    assert counts()[3] == before[3]


def test_the_hall_screen_carries_the_confirmation_byte_for_byte():
    assert rg(CONFIRM, "frontend/src/features/admin", fixed=True), "SCR-ADM-05's withdrawal confirmation is missing"


def _as(client, user_id: int, role: str) -> None:
    """Switch the client's session cookie to another account, minted with the product's own token function."""
    from app.core.security import SESSION_COOKIE, issue_session_token
    from tests.dbkit import app_settings

    client.cookies.set(SESSION_COOKIE, issue_session_token(user_id=user_id, role=role, password_version=1,
                                                           now=client.clock.now(), settings=app_settings(client.db)))


def test_the_booking_and_the_report_still_name_the_withdrawn_hall(cached_client):
    c = cached_client
    admin = sign_in(c)
    hall, category = make_screen(c.db, name="Hall Withdrawn 17"), make_category(c.db)
    seat = make_seat(c.db, hall, "C12", category, grid=(3, 12))
    st = make_showtime(c.db, hall, make_movie(c.db), "2026-10-20T10:00:00Z", "2026-10-20T12:00:00Z")
    customer = insert_user(c.db, role="customer")
    ref = new_reference()  # a valid stored reference, check character included
    insert_booking(c.db, user_id=customer, reference=ref,
                   showtime={"showtime_id": st, "seat_id": seat, "seat_category_id": category}, price_paise=25000)
    report = lambda: c.get("/api/reports/showtimes", params={"period": "day", "date": "2026-10-20", "screen_id": hall})  # noqa: E731
    before = report()
    assert before.status_code == 200, before.text
    assert [(r["showtime_id"], r["screen_name"]) for r in before.json()["rows"]] == [(st, "Hall Withdrawn 17")]
    assert c.patch(f"/api/admin/screens/{hall}", json={"version": 1, "is_active": False}).status_code == 200
    after = report()
    assert after.status_code == 200, after.text
    assert after.json()["rows"] == before.json()["rows"]
    _as(c, customer, "customer")
    mine = c.get(f"/api/me/bookings/FR-{ref[:4]}-{ref[4:]}")
    assert mine.status_code == 200, mine.text
    assert mine.json()["hall_name"] == "Hall Withdrawn 17"
    assert admin

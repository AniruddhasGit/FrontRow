"""S-ADM-13 - affected_future_showtimes, P-ADM-11's one rule, at one injected instant.

This module's database holds exactly the four worked-example showtimes and no others.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from tests.adm.kit import client, make_category, make_movie, make_screen, make_seats, make_showtime, sign_in  # noqa: F401
from tests.dbkit import app_settings, owner_sql
from tests.test_health import ok_probe

AT_0900 = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)


def _four(db):
    if owner_sql(db, "SELECT count(*) FROM showtime") == [(0,)]:
        hall, other = make_screen(db), make_screen(db, active=False)  # an out-of-service hall still counts
        make_seats(db, hall, 1)
        make_seats(db, other, 1)
        film = make_movie(db)
        for screen, starts in ((hall, "2026-08-14T07:30:00Z"), (other, "2026-08-14T08:50:00Z"),
                               (hall, "2026-08-14T09:00:00Z"), (hall, "2026-08-16T14:00:00Z")):
            make_showtime(db, screen, film, starts, starts.replace("T", " ")[:11] + "23:59:00Z")
    assert owner_sql(db, "SELECT count(*) FROM showtime") == [(4,)]


def test_plus_15_counts_3(client):
    sign_in(client)
    _four(client.db)
    client.clock._now = AT_0900
    body = client.get("/api/admin/seat-categories").json()
    assert (body["affected_future_showtimes"], body["evaluated_at_utc"]) == (3, "2026-08-14T09:00:00Z")


def test_minus_15_counts_1(migrated_db, clock):
    _four(migrated_db)
    app = create_app(app_settings(migrated_db, SALES_CUTOFF_MINUTES="-15"), clock=clock,
                     probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(app) as c:
        c.clock, c.db = clock, migrated_db
        sign_in(c)
        clock._now = AT_0900
        assert c.get("/api/admin/seat-categories").json()["affected_future_showtimes"] == 1


def test_the_read_and_the_write_are_evaluated_separately_and_never_compared(client):
    sign_in(client)
    _four(client.db)
    cat = make_category(client.db, uplift=1250)
    client.clock._now = AT_0900
    assert client.get("/api/admin/seat-categories").json()["affected_future_showtimes"] == 3
    client.clock.advance(600)  # 09:10:00Z - B's threshold 09:05 is now past
    read = client.get("/api/admin/seat-categories").json()
    assert set(read) == {"items", "affected_future_showtimes", "evaluated_at_utc"}  # no warning, no confirmation key
    r = client.patch(f"/api/admin/seat-categories/{cat}", json={"version": 1, "uplift_basis_points": 1500})
    assert r.status_code == 200
    body = r.json()
    assert (body["affected_future_showtimes"], body["evaluated_at_utc"]) == (2, "2026-08-14T09:10:00Z")
    assert set(body) == {"id", "name", "uplift_basis_points", "affected_future_showtimes", "evaluated_at_utc", "version"}

"""S-ADM-04 - every local time resolves from the cinema row, never from CINEMA_TIMEZONE (P-ADM-26).

NOT covered, and why: the boot-time WARNING lines (row/variable mismatch, unseeded venue), the boot
statement listener, and "CINEMA_TIMEZONE unset exits non-zero" are the app lifespan's (app/main.py) and
the configuration's (app/core/config.py, which gives the variable a default) - foundation files. The
"exactly two files" ripgrep needs scripts/seed.py, which the seed lane writes.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.adm.kit import make_cinema, make_movie, make_screen, make_seats, make_showtime, sign_in
from tests.dbkit import app_settings, owner_sql
from tests.test_health import ok_probe
from tests.xct._support import rg


def test_no_request_path_code_names_cinema_timezone():
    for tree in ("backend/app/api", "backend/app/domain", "backend/app/models", "backend/app/workers", "backend/app/jobs",
                 "frontend/src"):
        assert rg("CINEMA_TIMEZONE", tree) == [], tree
    assert {h[0] for h in rg("CINEMA_TIMEZONE", "backend/app")} == {"backend/app/core/config.py"}


def test_the_row_zone_wins_over_the_variable_and_a_zone_change_rewrites_no_instant(migrated_db, clock):
    app = create_app(app_settings(migrated_db, CINEMA_TIMEZONE="UTC"), clock=clock,
                     probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(app) as client:
        client.clock, client.db = clock, migrated_db
        sign_in(client)
        venue = make_cinema(migrated_db, timezone="Asia/Kolkata")
        hall = make_screen(migrated_db, venue)
        make_seats(migrated_db, hall, 1)
        st = make_showtime(migrated_db, hall, make_movie(migrated_db), "2026-08-14T14:00:00Z", "2026-08-14T16:00:00Z")
        day = client.get("/api/admin/showtimes", params={"screen_id": hall, "date": "2026-08-14"}).json()["items"]
        assert [(i["id"], i["starts_at"]) for i in day] == [(st, "2026-08-14T19:30:00")]  # 14:00 + 05:30
        assert client.get("/health/ready").status_code == 200
        stored = owner_sql(migrated_db, "SELECT starts_at FROM showtime WHERE id = %s", (st,))
        assert client.patch(f"/api/admin/cinemas/{venue}", json={"version": 1, "timezone": "Asia/Dubai"}).status_code == 200
        assert owner_sql(migrated_db, "SELECT starts_at FROM showtime WHERE id = %s", (st,)) == stored
        day = client.get("/api/admin/showtimes", params={"screen_id": hall, "date": "2026-08-14"}).json()["items"]
        assert [i["starts_at"] for i in day] == ["2026-08-14T18:00:00"]  # 14:00 + 04:00


def test_no_zone_column_on_showtime_or_screen(migrated_db):
    assert owner_sql(migrated_db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                                  "AND table_name IN ('showtime','screen') AND column_name LIKE '%%timezone%%'") == [(0,)]

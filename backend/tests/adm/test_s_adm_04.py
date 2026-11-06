"""S-ADM-04 - every local time resolves from the cinema row, never from CINEMA_TIMEZONE (P-ADM-26).

The boot clauses run the REAL boot path, app.server.main("api"), against a throwaway database and the compose
Redis, with only uvicorn's serve() replaced by a stand-in that runs the lifespan and asks GET /health/ready (real
probes, not stubs). The boot check is app/core/config.py venue_zone_check (one SELECT on cinema).
"""

from __future__ import annotations

import json
import logging
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.main import create_app
from tests.adm.kit import make_cinema, make_movie, make_screen, make_seats, make_showtime, sign_in
from tests.dbkit import app_settings, create_database, drop_database, owner_sql
from tests.test_health import ok_probe
from tests.xct._support import rg


def test_no_request_path_code_names_cinema_timezone():
    for tree in ("backend/app/api", "backend/app/domain", "backend/app/models", "backend/app/workers", "backend/app/jobs",
                 "frontend/src"):
        assert rg("CINEMA_TIMEZONE", tree) == [], tree
    hits = rg("CINEMA_TIMEZONE", "backend/app", "backend/migrations", "frontend/src", "scripts")
    assert {h[0] for h in hits} == {"backend/app/core/config.py", "scripts/seed.py"}


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


@pytest.fixture(scope="module")
def seeded_db():
    db = create_database(migrate=True)
    owner_sql(db, "INSERT INTO cinema (name, timezone, version) VALUES ('Venue boot', 'Asia/Kolkata', 1)")
    yield db
    drop_database(db)


@pytest.fixture(scope="module")
def empty_db():
    db = create_database(migrate=True)
    yield db
    drop_database(db)


def _boot(db, env, capsys, zone: str | None):
    """app.server.main('api') end to end; returns (exit code, JSON lines, every statement of the boot, ready status)."""
    import app.server as server

    env.setenv("DATABASE_URL", db.app_url)
    env.setenv("REDIS_URL", os.environ["TEST_REDIS_URL"])
    if zone is not None:
        env.setenv("CINEMA_TIMEZONE", zone)
    statements: list[str] = []
    ready: list[int] = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    def fake_serve(settings, app):
        with TestClient(app) as c:  # the lifespan's startup has run: boot is over, so the listener stops here
            event.remove(Engine, "before_cursor_execute", listener)
            ready.append(c.get("/health/ready").status_code)
        return 0

    env.setattr(server, "serve", fake_serve)
    event.listen(Engine, "before_cursor_execute", listener)
    try:
        code = server.main("api")
    finally:
        if event.contains(Engine, "before_cursor_execute", listener):
            event.remove(Engine, "before_cursor_execute", listener)
        logging.getLogger().handlers.clear()
    captured = capsys.readouterr()
    lines = [json.loads(ln) for ln in captured.out.splitlines() if ln.strip()]
    return code, lines, statements, ready, captured.err


def _warnings(lines):
    return [ln for ln in lines if ln["level"] == "WARNING"]


def test_a_row_variable_mismatch_is_one_warning_at_boot_and_ready_is_200(seeded_db, valid_env, capsys):
    venue = owner_sql(seeded_db, "SELECT id FROM cinema")[0][0]
    code, lines, statements, ready, _ = _boot(seeded_db, valid_env, capsys, "UTC")
    assert code == 0 and ready == [200]
    warnings = _warnings(lines)
    assert len(warnings) == 1, warnings
    w = warnings[0]
    assert (w["cinema_id"], w["row_timezone"], w["cinema_timezone_variable"]) == (venue, "Asia/Kolkata", "UTC")
    # The whole boot sequence: only SELECTs against cinema, no UPDATE and no ALTER.
    assert statements, "the listener saw nothing - it would pass vacuously"
    for s in statements:
        assert s.lstrip().upper().startswith("SELECT") and " cinema" in s.lower(), s
        assert "UPDATE" not in s.upper() and "ALTER" not in s.upper(), s


def test_unset_variable_boots_with_asia_kolkata_and_no_warning(seeded_db, valid_env, capsys):
    from app.core.config import load_settings

    valid_env.setenv("DATABASE_URL", seeded_db.app_url)
    assert load_settings().CINEMA_TIMEZONE == "Asia/Kolkata"
    code, lines, _, ready, _ = _boot(seeded_db, valid_env, capsys, None)
    assert code == 0 and ready == [200]
    assert _warnings(lines) == []  # the row says Asia/Kolkata and so does the default


def test_an_unresolvable_zone_exits_nonzero_before_serving_and_names_the_variable(seeded_db, valid_env, capsys):
    import app.server as server

    served: list[int] = []
    valid_env.setattr(server, "serve", lambda settings, app: served.append(1) or 0)
    valid_env.setenv("DATABASE_URL", seeded_db.app_url)
    valid_env.setenv("CINEMA_TIMEZONE", "Mars/Olympus_Mons")
    code = server.main("api")
    out = capsys.readouterr()
    assert code != 0 and served == []  # serve() - the port bind - was never reached
    assert "CINEMA_TIMEZONE" in out.err and "CINEMA_TIMEZONE" in out.out


def test_an_unseeded_venue_is_one_warning_at_boot(empty_db, valid_env, capsys):
    assert owner_sql(empty_db, "SELECT count(*) FROM cinema") == [(0,)]
    code, lines, statements, ready, _ = _boot(empty_db, valid_env, capsys, None)
    assert code == 0 and ready == [200]
    warnings = _warnings(lines)
    assert len(warnings) == 1 and "not been seeded" in warnings[0]["message"], warnings
    assert statements and all(s.lstrip().upper().startswith("SELECT") and " cinema" in s.lower() for s in statements)

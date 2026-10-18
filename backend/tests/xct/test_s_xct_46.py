"""S-XCT-46 (PRD P-XCT-30): the seed writes no audit row, warns once before the layout freezes, writes in the
fixed order, is idempotent, and is the only exemption from the same-transaction audit rule.

Run order matters inside this module: the admin-route sweep changes seeded rows, so it is the last test.
"""

from __future__ import annotations

import re
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.security import SESSION_COOKIE, issue_session_token
from app.main import create_app
from tests.adm.kit import routes
from tests.conftest import FakeClock
from tests.dbkit import app_settings, create_database, drop_database, owner_sql
from tests.seed.kit import DOMAIN, NOW, empty_db, one, run_seed, run_seed_process, seed, seeded, table_counts  # noqa: F401
from tests.test_health import ok_probe
from tests.xct._support import DEPLOY, rg

NOTICE = ("NOTICE: the next write freezes the seat layout of all six halls. Renumbering, removing or "
          "recategorising a seat is refused with 409 LAYOUT_FROZEN from now on.")


def test_a_fresh_seed_writes_no_audit_row_and_no_service_account(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM audit_log") == 0
    assert one(db, "SELECT count(*) FROM audit_log WHERE actor_user_id IS NULL") == 0
    assert one(db, "SELECT count(*) FROM users WHERE email NOT LIKE '%%@' || %s", (DOMAIN,)) == 0
    assert one(db, "SELECT count(*) FROM movie WHERE title NOT LIKE 'DEMO %%'") == 0


def test_the_notice_is_printed_exactly_once_before_the_first_showtime_insert():
    db = create_database(migrate=True)
    try:
        events: list[tuple[str, str]] = []
        code, _ = run_seed(db.app_url, out=lambda line: events.append(("out", line)), trace=events.append)
        assert code == 0
        outs = [i for i, (kind, text) in enumerate(events) if kind == "out" and text == NOTICE]
        assert len(outs) == 1
        first_showtime = next(i for i, (kind, text) in enumerate(events) if kind == "sql" and text.startswith("INSERT INTO showtime "))
        assert outs[0] < first_showtime
        # nothing else is printed before it
        assert [t for k, t in events[:first_showtime] if k == "out"] == [NOTICE]
        # vocabulary, then screens and seats, then films, then showtimes
        firsts = []
        for table in ("language", "certification", "genre", "format", "screen", "seat", "movie", "showtime"):
            firsts.append(next(i for i, (kind, text) in enumerate(events) if kind == "sql" and text.startswith(f"INSERT INTO {table} ")))
        assert firsts == sorted(firsts)
        assert max(firsts[:4]) < firsts[4] < firsts[5] < firsts[6] < firsts[7]
    finally:
        drop_database(db)


def test_the_seed_never_reads_input_and_completes_with_stdin_closed():
    assert rg(r"input\(|sys\.stdin", "scripts/seed.py") == []
    db = create_database(migrate=True)
    try:
        result = run_seed_process(db.app_url)
        assert result.returncode == 0, result.stderr
        assert result.stdout.count(NOTICE) == 1
        assert one(db, "SELECT count(*) FROM showtime") == 720
    finally:
        drop_database(db)


def test_with_the_vocabulary_insert_a_no_op_the_seed_exits_non_zero_and_writes_no_film(empty_db, monkeypatch):
    before = table_counts(empty_db)
    monkeypatch.setattr(seed, "insert_vocabulary", lambda db: None)
    code, _ = run_seed(empty_db.app_url)
    assert code != 0
    assert one(empty_db, "SELECT count(*) FROM movie") == 0
    assert table_counts(empty_db) == before  # one transaction: no partial catalogue of any kind


def test_a_second_run_changes_no_count_and_keeps_a_hand_changed_password(seeded):
    db, _ = seeded
    owner_sql(db, "UPDATE users SET password_hash = %s WHERE email = %s", ("$2b$" + "04$" + "h" * 53, f"customer-07@{DOMAIN}"))
    changed = one(db, "SELECT password_hash FROM users WHERE email = %s", (f"customer-07@{DOMAIN}",))
    before = table_counts(db)
    code, _ = run_seed(db.app_url, now=NOW + timedelta(days=1))
    assert code == 0
    assert table_counts(db) == before
    assert one(db, "SELECT password_hash FROM users WHERE email = %s", (f"customer-07@{DOMAIN}",)) == changed


def test_help_lists_the_wipe_command_and_the_docs_forbid_it_in_the_deployed_environment():
    result = run_seed_process(None, "--help", password=None)
    assert result.returncode == 0
    assert "--wipe-and-reseed" in result.stdout
    assert rg("The wipe-and-reseed command is never run against the deployed environment. Seeded rows there are "
              "permanent, because nothing is ever deleted.", "docs/30 Deployment", fixed=True)
    spec = (DEPLOY / "P2_SEED_TASK.md").read_text(encoding="utf-8")
    assert "Settle seat labelling before the first seeded showtime write." in spec
    assert "409 LAYOUT_FROZEN" in spec


def test_wipe_and_reseed_empties_and_seeds_again_with_the_owner():
    db = create_database(migrate=True)
    try:
        assert run_seed(db.app_url)[0] == 0
        owner_sql(db, "UPDATE movie SET synopsis = 'edited' WHERE title = 'DEMO MOVIE 01'")
        code, _ = run_seed(db.owner_url, "--wipe-and-reseed")
        assert code == 0
        assert one(db, "SELECT count(*) FROM movie WHERE synopsis = 'edited'") == 0
        assert one(db, "SELECT count(*) FROM booking") == 11003
    finally:
        drop_database(db)


@pytest.fixture(scope="module")
def admin_client(seeded):
    db, _ = seeded
    clock = FakeClock()
    application = create_app(app_settings(db), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    admin_id = one(db, "SELECT id FROM users WHERE email = %s", (f"admin-01@{DOMAIN}",))
    with TestClient(application, raise_server_exceptions=False) as c:
        c.cookies.set(SESSION_COOKIE, issue_session_token(user_id=admin_id, role="admin", password_version=1,
                                                          now=clock.now(), settings=app_settings(db)))
        c.db, c.app_ = db, application
        yield c


def _screen1_seat(db):
    return one(db, "SELECT seat.id FROM seat JOIN screen ON screen.id = seat.screen_id "
                   "WHERE screen.name = 'SCREEN 1' AND row_label = 'A' AND seat_number = 1")


def test_after_the_seed_three_layout_changes_are_each_refused_with_layout_frozen(admin_client):
    db = admin_client.db
    seat_id = _screen1_seat(db)
    other_category = one(db, "SELECT id FROM seat_category WHERE name = 'Premium'")
    for method, body in (("PATCH", {"row_label": "Z"}), ("PATCH", {"seat_category_id": other_category}), ("DELETE", None)):
        r = admin_client.request(method, f"/api/admin/seats/{seat_id}", json=body)
        assert r.status_code == 409, (method, body, r.text)
        assert r.json()["error"]["code"] == "LAYOUT_FROZEN"


def test_zz_every_admin_write_route_writes_exactly_one_audit_row(admin_client):
    """Runs last: it changes seeded rows. Every mounted POST/PATCH/PUT/DELETE under /api/admin has a request
    here that succeeds; a new write route without one fails the walk, so the sweep cannot go stale."""
    db, c = admin_client.db, admin_client
    mounted = {(m, r.path) for r in routes(c.app_) for m in getattr(r, "methods", ()) if m in {"POST", "PATCH", "PUT", "DELETE"}
               and r.path.startswith("/api/admin")}
    cinema_id = one(db, "SELECT id FROM cinema")
    film = one(db, "SELECT id FROM movie WHERE title = 'DEMO MOVIE 01'")
    day = (NOW + timedelta(days=5)).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
    state: dict[str, int] = {}

    def audits() -> int:
        return one(db, "SELECT count(*) FROM audit_log")

    steps = [
        ("PATCH", "/api/admin/cinemas/{cinema_id}", lambda: (f"/api/admin/cinemas/{cinema_id}", {"version": 1, "name": "DEMO CINEMA X"})),
        ("POST", "/api/admin/screens", lambda: ("/api/admin/screens", {"cinema_id": cinema_id, "name": "SWEEP HALL"})),
        ("PATCH", "/api/admin/screens/{screen_id}", lambda: (f"/api/admin/screens/{state['screen']}", {"version": 1, "name": "SWEEP HALL 2"})),
        ("POST", "/api/admin/seat-categories", lambda: ("/api/admin/seat-categories", {"name": "Sweep", "uplift_basis_points": 0})),
        ("PATCH", "/api/admin/seat-categories/{seat_category_id}",
         lambda: (f"/api/admin/seat-categories/{state['category']}", {"version": 1, "name": "Sweep 2"})),
        ("POST", "/api/admin/screens/{screen_id}/seats", lambda: (f"/api/admin/screens/{state['screen']}/seats", {"seats": [
            {"row_label": "A", "seat_number": 1, "grid_row": 1, "grid_col": 1, "seat_category_id": state["category"]}]})),
        ("PATCH", "/api/admin/seats/{seat_id}", lambda: (f"/api/admin/seats/{state['seat']}", {"grid_col": 2})),
        ("POST", "/api/admin/showtimes", lambda: ("/api/admin/showtimes", {
            "movie_id": film, "screen_id": state["screen"], "starts_at": f"{day}T11:00:00", "ends_at": f"{day}T13:00:00",
            "base_price_paise": 24999})),
        ("PATCH", "/api/admin/showtimes/{showtime_id}", lambda: (f"/api/admin/showtimes/{state['showtime']}",
                                                                 {"version": 1, "base_price_paise": 25999})),
        ("POST", "/api/admin/managers", lambda: ("/api/admin/managers", {"email": f"sweep-manager@{DOMAIN}", "screen_ids": []})),
        ("PUT", "/api/admin/managers/{user_id}/screens", lambda: (f"/api/admin/managers/{state['manager']}/screens",
                                                                  {"screen_ids": [state["screen"]]})),
        ("DELETE", "/api/admin/seats/{seat_id}", lambda: (f"/api/admin/seats/{state['spare_seat']}", None)),
    ]
    assert {(m, p) for m, p, _ in steps} == mounted
    for method, template, build in steps:
        if template == "/api/admin/seats/{seat_id}" and method == "DELETE":
            # the sweep hall now has a showtime, so its seat is frozen: delete a seat on a second, empty hall
            # (its own two set-up writes are not counted; each was audited like any other)
            r = c.post("/api/admin/screens", json={"cinema_id": cinema_id, "name": "SWEEP HALL B"})
            hall = r.json()["id"]
            r = c.post(f"/api/admin/screens/{hall}/seats", json={"seats": [
                {"row_label": "A", "seat_number": 1, "grid_row": 1, "grid_col": 1, "seat_category_id": state["category"]}]})
            state["spare_seat"] = r.json()["items"][0]["id"]
        path, body = build()
        before = audits()
        r = c.request(method, path, json=body)
        assert r.status_code < 300, (method, path, r.status_code, r.text)
        assert audits() == before + 1, (method, path)
        data = r.json() if r.content else {}
        if template == "/api/admin/screens":
            state["screen"] = data["id"]
        elif template == "/api/admin/seat-categories":
            state["category"] = data["id"]
        elif template.endswith("/seats") and method == "POST":
            state["seat"] = data["items"][0]["id"]
        elif template == "/api/admin/showtimes":
            state["showtime"] = data["id"]
        elif template == "/api/admin/managers":
            state["manager"] = data["user_id"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)

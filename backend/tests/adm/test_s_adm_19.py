"""S-ADM-19 - withdraw instead of deleting, everywhere (P-ADM-20).

NOT covered: DELETE on /api/admin/movies/{id} and /api/admin/lookups/... answering 405 - those paths do
not exist until Phase 6, so today they answer 404 (asserted below as the current, honest state); and the
byte comparison of GET /api/me/bookings/{reference} (Phase 4).
"""

from __future__ import annotations

from tests.adm.kit import client, make_cinema, make_screen, sign_in, strip_request_id  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import mounted_routes, rg, zone_c

GENERIC_405 = "That action is not available. Nothing was changed."


def test_exactly_one_delete_route_under_api_admin_and_it_is_the_seat(client):
    deletes = sorted(p for m, p in mounted_routes(client.app) if m == "DELETE" and p.startswith("/api/admin"))
    assert deletes == ["/api/admin/seats/{seat_id}"]


def test_delete_on_every_never_deleted_entity_is_the_same_405(client):
    sign_in(client)
    cinema = make_cinema(client.db)
    hall = make_screen(client.db, cinema)
    bodies = []
    for path in (f"/api/admin/showtimes/1", f"/api/admin/screens/{hall}", f"/api/admin/cinemas/{cinema}"):
        r = client.delete(path)
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (405, "METHOD_NOT_ALLOWED", GENERIC_405)
        bodies.append(strip_request_id(r.json()))
    assert bodies[0] == bodies[1] == bodies[2]


def test_the_phase_6_addresses_do_not_exist_yet(client):
    sign_in(client)
    for path in ("/api/admin/movies/1", "/api/admin/lookups/genre", "/api/admin/lookups/genre/1"):
        assert client.delete(path).status_code == 404  # becomes 405 when EP-ADM-01..08/25..27 are mounted


def test_only_seat_and_assignment_rows_are_ever_deleted_and_nothing_cascades(client):
    hits = rg(r"DELETE FROM|[.]delete[(][)]|\bdelete[(]", "backend/app")
    tables = {line.split("delete(")[1].split(")")[0].strip() for _, _, line in hits if "delete(" in line and "@router" not in line}
    assert tables <= {"seat", "msa"}  # msa is manager_screen_assignment, imported under that name
    assert owner_sql(client.db, """
        SELECT count(*) FROM information_schema.referential_constraints rc
        JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name
         AND k.constraint_schema = rc.constraint_schema
        WHERE rc.constraint_schema = current_schema() AND rc.delete_rule = 'CASCADE'""") == [(0,)]
    rules = owner_sql(client.db, "SELECT DISTINCT delete_rule FROM information_schema.referential_constraints "
                                 "WHERE constraint_schema = current_schema()")
    assert {r[0] for r in rules} <= {"RESTRICT", "NO ACTION"}


def test_no_pruning_or_scheduled_deletion_exists_in_the_code():
    assert rg(r"retention|prune|purge|vacuum_old|cron|crontab|APScheduler|schedule[.]every", "backend/app",
              "backend/migrations", "scripts", *zone_c(".github/workflows")) == []

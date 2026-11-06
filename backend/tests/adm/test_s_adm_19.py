"""S-ADM-19 - withdraw instead of deleting, everywhere (P-ADM-20).

NOT covered: the byte comparison of GET /api/me/bookings/{reference} after withdrawing a film, a hall and a seat.
"""

from __future__ import annotations

from tests.adm.kit import client, make_cinema, make_lookup, make_screen, new_film, sign_in, strip_request_id  # noqa: F401
from tests.dbkit import owner_sql
from tests.xct._support import mounted_routes, rg, zone_c

GENERIC_405 = "That action is not available. Nothing was changed."


def test_exactly_one_delete_route_under_api_admin_and_it_is_the_seat(client):
    deletes = sorted(p for m, p in mounted_routes(client.app) if m == "DELETE" and p.startswith("/api/admin"))
    # Plus EP-ADM-32 since SRC-008 ROLE-1 ADDENDUM / S-ADM-30 (removing a granted email); the criterion's "exactly one"
    # predates that ruling and is raised for a Bible amendment. Still no DELETE for any never-deleted entity.
    assert deletes == ["/api/admin/admin-grants/{grant_id}", "/api/admin/seats/{seat_id}"]


def test_delete_on_every_never_deleted_entity_is_the_same_405(client):
    sign_in(client)
    cinema = make_cinema(client.db)
    hall = make_screen(client.db, cinema)
    film, genre = new_film(client)["id"], make_lookup(client.db, "genre")
    bodies = []
    for path in (f"/api/admin/movies/{film}", "/api/admin/showtimes/1", f"/api/admin/screens/{hall}",
                 f"/api/admin/cinemas/{cinema}", "/api/admin/lookups/genre", f"/api/admin/lookups/genre/{genre}"):
        r = client.delete(path)
        assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"]) == (405, "METHOD_NOT_ALLOWED", GENERIC_405)
        bodies.append(strip_request_id(r.json()))
    assert len(bodies) == 6 and all(b == bodies[0] for b in bodies)


def test_only_seat_and_assignment_rows_are_ever_deleted_and_nothing_cascades(client):
    # The AC's pattern, plus SQLAlchemy Core's delete(<table>) spelling, which it cannot see. A METHOD called delete -
    # @router.delete, or a Redis client's .delete(key) on a cache key (app/core/cache.py) - removes no row: excluded.
    hits = rg(r"DELETE FROM|[.]delete[(][)]|(?<![.\w])delete[(]", "backend/app")
    tables = {line.split("delete(")[1].split(")")[0].strip() for _, _, line in hits if "delete(" in line and "@router" not in line}
    # movie_genre: a film's genres ARE its join rows, so a genre edit replaces them (P-ADM-02, EP-ADM-04 genre_ids), and
    # datamodel.json grants DELETE on exactly seat, manager_screen_assignment and movie_genre. The AC's two-table list
    # predates EP-ADM-04 and is reported as a doc defect. No film, booking or audit row is deleted anywhere.
    # admin_grant: SRC-008 ROLE-1 ADDENDUM / S-ADM-30 rule that removing a granted email deletes its grant row; no
    # booking reaches it (its only foreign key points at users). Raised against S-XCT-09's "exactly two entities".
    assert {"seat", "msa"} <= tables <= {"seat", "msa", "movie_genre", "admin_grant"}  # msa is manager_screen_assignment
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

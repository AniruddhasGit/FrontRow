"""S-ADM-29 - keep licensed content out of the product (P-ADM-22).

Almost everything this criterion asserts belongs to other lanes: the seed's names and its one poster
(scripts/seed.py, the seed lane), POST /api/admin/movies (Phase 6) and GET /api/movies/{id}/poster
(Phase 3). The schema clause is the one this lane can prove.
"""

from __future__ import annotations

from tests.dbkit import owner_sql


def test_the_movie_table_has_no_provenance_or_licence_column(migrated_db):
    assert owner_sql(migrated_db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND "
                                  "table_name = 'movie' AND column_name IN ('provenance','attribution','source','license',"
                                  "'licence','credit')") == [(0,)]

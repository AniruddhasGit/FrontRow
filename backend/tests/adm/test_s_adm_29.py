"""S-ADM-29 - keep licensed content out of the product (P-ADM-22).

The seed is run against an empty database (tests/seed/kit.py `seeded`) and its rows are read back one by one.

NOT met, and why the row stays Blocked: the cell requires every seeded language name to match ^DEMO [A-Z]+ [0-9]+$,
but S-XCT-44's own cell names them DEMO LANGUAGE A, B and C, which scripts/seed.py writes. Two Bible cells disagree;
which one wins is not this test's to decide, so the language names are asserted against S-XCT-44's DEMO prefix only and
the certification, genre and format names against this cell's regex.
"""

from __future__ import annotations

import inspect
import re

from fastapi.testclient import TestClient

from app.api import browse
from app.domain.posters import S3Posters
from app.main import create_app
from tests.adm.kit import client, film_body, routes, sign_in  # noqa: F401
from tests.dbkit import app_settings, owner_sql
from tests.seed.kit import seeded  # noqa: F401
from tests.test_health import ok_probe
from tests.xct._support import REPO, rg

VOCAB = re.compile(r"^DEMO [A-Z]+ [0-9]+$")


def test_the_movie_table_has_no_provenance_or_licence_column(migrated_db):
    assert owner_sql(migrated_db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND "
                                  "table_name = 'movie' AND column_name IN ('provenance','attribution','source','license',"
                                  "'licence','credit')") == [(0,)]


def test_every_seeded_title_and_venue_name_is_demonstration_content(seeded):
    db, _ = seeded
    titles = [t for (t,) in owner_sql(db, "SELECT title FROM movie ORDER BY id")]
    assert titles and all(re.fullmatch(r"DEMO MOVIE \d{2}", t) for t in titles), titles
    assert owner_sql(db, "SELECT count(*) FROM movie WHERE title !~ '^DEMO MOVIE [0-9]{2}$'") == [(0,)]
    cinemas = [n for (n,) in owner_sql(db, "SELECT name FROM cinema")]
    assert cinemas and all(re.fullmatch(r"DEMO CINEMA", n) for n in cinemas), cinemas
    screens = [n for (n,) in owner_sql(db, "SELECT name FROM screen")]
    assert screens and all(re.fullmatch(r"SCREEN [1-6]", n) for n in screens), screens


def test_every_seeded_vocabulary_name_is_demonstration_content(seeded):
    db, _ = seeded
    for table in ("certification", "genre", "format"):
        names = [n for (n,) in owner_sql(db, f"SELECT name FROM {table}")]
        assert names and all(VOCAB.fullmatch(n) for n in names), (table, names)
    languages = [n for (n,) in owner_sql(db, "SELECT name FROM language")]
    assert languages and all(n.startswith("DEMO LANGUAGE ") for n in languages), languages  # S-XCT-44's names, see above


def test_one_committed_poster_shared_by_every_seeded_film_and_nothing_fetched(seeded):
    db, _ = seeded
    assert (REPO / "scripts" / "assets" / "placeholder_poster.png").is_file()
    assert len(owner_sql(db, "SELECT DISTINCT poster_object_key FROM movie")) == 1
    pattern = r"http://|https://|requests[.]|httpx[.]|urllib|boto3[.]client[(].s3.[)][.]download|urlretrieve"
    assert rg(pattern, "scripts/seed.py") == []


def test_the_poster_route_checks_no_attribution_and_redirects_a_seeded_film(seeded):
    db, _ = seeded
    application = create_app(app_settings(db), probes=[ok_probe("postgres"), ok_probe("redis")])
    route = next(r for r in routes(application) if r.path == "/api/movies/{movie_id}/poster")
    assert route.dependant.dependencies == []
    assert "attribution" not in inspect.getsource(browse.get_poster).lower()
    film = owner_sql(db, "SELECT id FROM movie ORDER BY id LIMIT 1")[0][0]
    with TestClient(application, raise_server_exceptions=False) as c:
        c.app.state.posters = S3Posters(c.app.state.settings)  # presigns offline, as in test_s_brw_18
        r = c.get(f"/api/movies/{film}/poster", follow_redirects=False)
    assert r.status_code == 302, r.text


def test_the_admin_may_type_any_title_of_1_to_200_characters(client):
    sign_in(client)
    for title in ("X", "Ein Film ohne DEMO", "t" * 200):
        r = client.post("/api/admin/movies", json=film_body(client.db, title=title))
        assert r.status_code == 201, (title, r.text)

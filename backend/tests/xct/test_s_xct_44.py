"""S-XCT-44 (PRD P-XCT-30): the seed creates one cinema, six halls, the lookup vocabulary and eight published
placeholder films - computed, never typed - and docs/06 DataModel/seed/expected_summary.json is the oracle.

NOT covered here (the row stays open on them, see the lane report): the poster written through
app.domain.posters (that function is the Phase 6 poster upload, S-ADM-25), and GET /api/movies plus the
rendered landing page (the Phase 3 browse lane).
"""

from __future__ import annotations

import math
import re

import pytest

from app.domain.pricing import seat_price_paise
from tests.dbkit import owner_sql
from tests.seed.kit import SUMMARY, empty_db, one, run_seed, seed, seeded, table_counts  # noqa: F401
from tests.xct._support import rg


def test_the_cinema_is_demo_cinema_in_asia_kolkata(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM cinema") == 1
    assert one(db, "SELECT name || '|' || timezone FROM cinema") == "DEMO CINEMA|Asia/Kolkata"


def test_six_screens_carry_the_layout_of_the_oracle(seeded):
    db, _ = seeded
    for s in SUMMARY["screens"]:
        name = f"SCREEN {s['screen']}"
        assert re.fullmatch(SUMMARY["screen_name_pattern"], name)
        rows = one(db, "SELECT count(DISTINCT seat.row_label) FROM seat JOIN screen ON screen.id = seat.screen_id "
                       "WHERE screen.name = %s", (name,))
        cols = one(db, "SELECT max(seat.seat_number) FROM seat JOIN screen ON screen.id = seat.screen_id WHERE screen.name = %s",
                   (name,))
        seats = one(db, "SELECT count(*) FROM seat JOIN screen ON screen.id = seat.screen_id WHERE screen.name = %s", (name,))
        labels = one(db, "SELECT string_agg(DISTINCT seat.row_label, '' ORDER BY seat.row_label) FROM seat "
                         "JOIN screen ON screen.id = seat.screen_id WHERE screen.name = %s", (name,))
        assert (rows, cols, seats, labels) == (s["rows"], s["cols"], s["seats"], s["row_labels"])
        assert rows * cols == seats
    assert one(db, "SELECT count(*) FROM screen") == 6
    assert one(db, "SELECT count(*) FROM seat") == SUMMARY["tables"]["seat"]["rows"]


def test_no_row_label_contains_i_and_screen_1_ends_at_j(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM seat WHERE row_label LIKE '%%I%%'") == 0
    assert one(db, "SELECT string_agg(DISTINCT row_label, ' ' ORDER BY row_label) FROM seat JOIN screen "
                   "ON screen.id = seat.screen_id WHERE screen.name = 'SCREEN 1'") == "A B C D E F G H J"


def test_seats_number_from_1_left_to_right_and_labels_are_unique(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM (SELECT screen_id, row_label, seat_number FROM seat GROUP BY 1, 2, 3 "
                   "HAVING count(*) > 1) x") == 0
    assert one(db, "SELECT count(*) FROM seat WHERE seat_number <> grid_col OR seat_number < 1") == 0
    labels = {r + str(n) for r, n in owner_sql(
        db, "SELECT row_label, seat_number FROM seat")}
    assert {"A1", "A10", "J20"} <= labels


@pytest.mark.parametrize("rows,expected", [(9, (5, 3, 1)), (10, (5, 3, 2)), (11, (6, 4, 1)), (12, (6, 4, 2))])
def test_bands_are_computed_with_ceil_never_typed(rows, expected):
    assert seed.bands(rows) == expected
    assert expected[0] == math.ceil(rows * 5 / 10) and expected[1] == math.ceil(rows * 3 / 10)


def test_each_band_reads_back_from_the_database(seeded):
    db, _ = seeded
    for s in SUMMARY["screens"]:
        for band in s["bands"]:
            got = one(db, "SELECT count(*) FROM seat JOIN seat_category c ON c.id = seat.seat_category_id "
                          "JOIN screen ON screen.id = seat.screen_id WHERE screen.name = %s AND c.name = %s "
                          "AND seat.row_label = ANY(%s)", (f"SCREEN {s['screen']}", band["category"], list(band["row_labels"])))
            total = one(db, "SELECT count(*) FROM seat JOIN seat_category c ON c.id = seat.seat_category_id "
                            "JOIN screen ON screen.id = seat.screen_id WHERE screen.name = %s AND c.name = %s",
                        (f"SCREEN {s['screen']}", band["category"]))
            assert got == total == band["seats"], (s["screen"], band)
    assert [one(db, "SELECT count(*) FROM seat JOIN seat_category c ON c.id = seat.seat_category_id "
                    "JOIN screen ON screen.id = seat.screen_id WHERE screen.name = 'SCREEN 1' AND c.name = %s", (n,))
            for n in ("Standard", "Premium", "Recliner")] == [50, 30, 10]


def test_three_category_prices_come_from_seat_price_paise(seeded):
    db, _ = seeded
    base = one(db, "SELECT DISTINCT base_price_paise FROM showtime")
    for cat in SUMMARY["seat_categories"]:
        uplift = one(db, "SELECT uplift_basis_points FROM seat_category WHERE name = %s", (cat["name"],))
        assert uplift == cat["uplift_basis_points"]
        assert seat_price_paise(base, uplift) == cat["price_paise"]
        # and what the seed stored on every booked seat of that category is the same function's answer
        assert one(db, "SELECT count(*) FROM booking_seat bs JOIN seat_category c ON c.id = bs.seat_category_id "
                       "WHERE c.name = %s AND bs.price_paise <> %s", (cat["name"], cat["price_paise"])) == 0
    assert [seat_price_paise(24999, u) for u in (0, 1250, 3333)] == [24999, 28124, 33331]


def test_eleven_demo_lookup_rows_exist(seeded):
    db, _ = seeded
    names = {r for (r,) in owner_sql(
        db, "SELECT name FROM language UNION ALL SELECT name FROM certification UNION ALL SELECT name FROM genre "
            "UNION ALL SELECT name FROM format")}
    assert names == {"DEMO LANGUAGE A", "DEMO LANGUAGE B", "DEMO LANGUAGE C", "DEMO RATING 1", "DEMO RATING 2",
                     "DEMO GENRE 1", "DEMO GENRE 2", "DEMO GENRE 3", "DEMO GENRE 4", "DEMO FORMAT 1", "DEMO FORMAT 2"}


def test_eight_films_all_published_inside_their_window_sharing_one_poster(seeded):
    db, _ = seeded
    from tests.seed.kit import NOW

    assert [t for (t,) in owner_sql(
        db, "SELECT title FROM movie ORDER BY title")] == [f"DEMO MOVIE {n:02d}" for n in range(1, 9)]
    assert one(db, "SELECT count(*) FROM movie WHERE published_at IS NULL OR NOT (display_from <= %s AND %s < display_until)",
               (NOW, NOW)) == 0
    assert one(db, "SELECT count(DISTINCT poster_object_key) FROM movie") == 1
    assert one(db, "SELECT count(*) FROM movie WHERE poster_object_key IS NULL") == 0
    # every showtime of every film falls inside that film's window
    assert one(db, "SELECT count(*) FROM showtime s JOIN movie m ON m.id = s.movie_id "
                   "WHERE NOT (m.display_from <= s.starts_at AND s.starts_at < m.display_until)") == 0


def test_film_vocabulary_is_assigned_by_index(seeded):
    db, _ = seeded
    for film in SUMMARY["films"]:
        row = owner_sql(
            db, "SELECT l.name, c.name, m.runtime_minutes FROM movie m JOIN language l ON l.id = m.language_id "
                "JOIN certification c ON c.id = m.certification_id WHERE m.title = %s", (film["title"],))
        assert row == [(film["language"], film["certification"], film["runtime_minutes"])]
        genres = sorted(g for (g,) in owner_sql(
            db, "SELECT g.name FROM movie_genre mg JOIN genre g ON g.id = mg.genre_id JOIN movie m ON m.id = mg.movie_id "
                "WHERE m.title = %s", (film["title"],)))
        assert genres == sorted(film["genres"])
    # the worked example, read back by SELECT
    assert owner_sql(
        db, "SELECT l.name, c.name, string_agg(g.name, ',' ORDER BY g.name) FROM movie m JOIN language l ON l.id = m.language_id "
            "JOIN certification c ON c.id = m.certification_id JOIN movie_genre mg ON mg.movie_id = m.id "
            "JOIN genre g ON g.id = mg.genre_id WHERE m.title = 'DEMO MOVIE 04' GROUP BY 1, 2") == [
        ("DEMO LANGUAGE A", "DEMO RATING 2", "DEMO GENRE 1,DEMO GENRE 4")]


def test_every_lookup_row_is_referenced_by_a_visible_film(seeded):
    db, _ = seeded
    from tests.seed.kit import NOW

    visible = "m.published_at IS NOT NULL AND m.display_from <= %(now)s AND %(now)s < m.display_until"
    unreferenced = one(db, f"""
        SELECT (SELECT count(*) FROM language x WHERE NOT EXISTS (SELECT 1 FROM movie m WHERE m.language_id = x.id AND {visible}))
             + (SELECT count(*) FROM certification x WHERE NOT EXISTS (SELECT 1 FROM movie m WHERE m.certification_id = x.id AND {visible}))
             + (SELECT count(*) FROM genre x WHERE NOT EXISTS (SELECT 1 FROM movie_genre mg JOIN movie m ON m.id = mg.movie_id
                                                              WHERE mg.genre_id = x.id AND {visible}))
             + (SELECT count(*) FROM format x WHERE NOT EXISTS (SELECT 1 FROM showtime s JOIN movie m ON m.id = s.movie_id
                                                               WHERE s.format_id = x.id AND {visible}))""", {"now": NOW})
    assert unreferenced == 0


def test_a_layout_that_disagrees_with_itself_exits_non_zero_naming_the_screen_before_any_write(empty_db, monkeypatch, capsys):
    before = table_counts(empty_db)
    monkeypatch.setattr(seed, "LAYOUT", [(1, 90, 9, 10), (2, 120, 10, 11)])
    code, _ = run_seed(empty_db.app_url)
    assert code != 0
    assert "SCREEN 2" in capsys.readouterr().err
    assert table_counts(empty_db) == before


def test_a_band_of_zero_rows_is_refused():
    with pytest.raises(seed.SeedError, match="SCREEN 9"):
        seed.check_layout([(9, 2, 1, 2)])


def test_the_seed_fetches_nothing_and_uses_no_fake_data_library_and_no_card_shaped_number():
    assert rg(r"https?://", "scripts/seed.py") == []
    assert rg(r"faker|mimesis|factory[_-]boy", "backend/requirements.txt", ignore_case=True) == []
    assert rg(r"\b(4[0-9]{12}([0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b", "scripts", "backend/tests") == []


def test_the_placeholder_poster_is_committed_beside_the_seed_and_is_a_flat_2_by_3_png():
    import struct

    data = seed.POSTER_FILE.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (400, 600)  # 2:3, inside P-ADM-03's 200..4000 x 300..6000


def test_the_cinema_row_takes_its_zone_from_cinema_timezone(empty_db):
    """P-ADM-26 point 1: CINEMA_TIMEZONE is the value the seed writes into the cinema row, never a literal."""
    from tests.seed.kit import NOW, PASSWORD, seed_env
    with seed_env(DATABASE_URL=empty_db.app_url, SEED_DEFAULT_PASSWORD=PASSWORD, BCRYPT_COST="4",
                  CINEMA_TIMEZONE="Europe/London"):
        assert seed.main([], now=NOW, out=lambda _line: None) == 0
    assert one(empty_db, "SELECT timezone FROM cinema") == "Europe/London"


def test_an_unknown_cinema_timezone_is_refused_before_any_write(empty_db):
    from tests.seed.kit import NOW, PASSWORD, seed_env
    with seed_env(DATABASE_URL=empty_db.app_url, SEED_DEFAULT_PASSWORD=PASSWORD, BCRYPT_COST="4",
                  CINEMA_TIMEZONE="Mars/Olympus"):
        assert seed.main([], now=NOW, out=lambda _line: None) == 78
    assert one(empty_db, "SELECT count(*) FROM cinema") == 0

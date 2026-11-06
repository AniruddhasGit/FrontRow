"""CR-001 Part A (docs/15 ChangeRequest/CR-001, A.2-A.3): six differently shaped halls and four films on fixed
screens. The expected shapes are typed here from the CR-001 A.3 table, never read back from scripts/seed.py.
"""

from __future__ import annotations

from tests.dbkit import owner_sql
from tests.seed.kit import seeded  # noqa: F401

# Screen -> per labelled row (front to back): category and the seat blocks between aisles. Typed from CR-003's table
# (which supersedes CR-001 A.3), never read back from scripts/seed.py.
def _h(spec: str) -> list[tuple[str, list[int]]]:
    out = []
    for part in spec.split(" | "):
        labels, cat, blocks = part.split()
        out += [(cat, [int(n) for n in blocks.split(",")])] * len(labels)
    return out


HALLS = {
    1: _h("A S 11 | BCD S 12 | EF P 12 | G P 13 | H R 6"),
    2: _h("ABC S 5,5 | D S 6,6 | EFGHJK P 6,6 | L R 3,3"),
    3: _h("A S 3,8,3 | BCD S 4,8,4 | EFGHJ P 4,8,4 | K R 2,4,2"),
    4: _h("A S 1,10,1 | BC S 2,10,2 | DE S 3,10,3 | F S 4,10,4 | G P 4,10,4 | HJ P 5,10,5 | K P 5,10,6 | L R 3,5,3"),
    5: _h("ABCD S 7,7 | E R 3,5,3 | FGHJKL P 3,10,3 | M P 4,10,4 | N P 4,10,5"),
    6: _h("ABC S 3,10,3 | DE S 4,10,4 | FGH P 4,10,4 | J R 2,5,3 | KLMN P 4,10,4"),
}
CAT = {"S": "Standard", "P": "Premium", "R": "Recliner"}


def _rows(db, screen: int) -> list[tuple[str, str, list[int]]]:
    """(row_label, category, sorted grid_cols) per row, front first."""
    return [(label, cat, sorted(cols)) for label, cat, _, cols in owner_sql(
        db, "SELECT seat.row_label, min(c.name), min(seat.grid_row), array_agg(seat.grid_col) FROM seat "
            "JOIN screen ON screen.id = seat.screen_id JOIN seat_category c ON c.id = seat.seat_category_id "
            "WHERE screen.name = %s GROUP BY 1 ORDER BY 3", (f"SCREEN {screen}",))]


def _blocks(cols: list[int], width: int) -> list[int]:
    """Seat counts of the runs of adjacent seats; a gap wider than one seat is an aisle."""
    out = [1]
    for a, b in zip(cols, cols[1:]):
        if b - a == width:
            out[-1] += 1
        else:
            out.append(1)
    return out


def test_each_hall_has_its_cr003_shape(seeded):
    db, _ = seeded
    for screen, want in HALLS.items():
        rows = _rows(db, screen)
        assert sum(sum(b) for _, b in want) == [90, 120, 150, 180, 200, 220][screen - 1]  # the table is self-consistent
        assert len(rows) == len(want), screen
        assert "I" not in "".join(label for label, _, _ in rows)
        for (label, cat, cols), (want_cat, want_blocks) in zip(rows, want):
            assert cat == CAT[want_cat], (screen, label)
            assert _blocks(cols, 2 if want_cat == "R" else 1) == want_blocks, (screen, label)


def test_each_film_plays_only_on_its_fixed_screens(seeded):
    db, _ = seeded
    got = {(t, s): (n, starts) for t, s, n, starts in owner_sql(
        db, "SELECT m.title, sc.name, count(*), string_agg(DISTINCT to_char(s.starts_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI'), ' ') "
            "FROM showtime s JOIN movie m ON m.id = s.movie_id JOIN screen sc ON sc.id = s.screen_id GROUP BY 1, 2")}
    slots, later = "11:00 14:30 18:00 21:30", "12:45 16:15 19:45 23:15"
    assert got == {
        ("DEMO MOVIE 01", "SCREEN 6"): (120, slots), ("DEMO MOVIE 01", "SCREEN 5"): (120, later),
        ("DEMO MOVIE 02", "SCREEN 4"): (120, slots), ("DEMO MOVIE 02", "SCREEN 3"): (120, later),
        ("DEMO MOVIE 03", "SCREEN 2"): (120, slots),
        ("DEMO MOVIE 04", "SCREEN 1"): (120, slots),
    }

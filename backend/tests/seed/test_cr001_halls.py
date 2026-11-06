"""CR-001 Part A (docs/15 ChangeRequest/CR-001, A.2-A.3): six differently shaped halls and four films on fixed
screens. The expected shapes are typed here from the CR-001 A.3 table, never read back from scripts/seed.py.
"""

from __future__ import annotations

from tests.dbkit import owner_sql
from tests.seed.kit import seeded  # noqa: F401

# Screen -> per labelled row (front A to back), the seat blocks between aisles. Typed from CR-001 A.3.
FAN = [10, 11, 12, 13, 14, 15, 15, 16, 17, 18, 19, 20]
HALLS = {
    1: [[10]] * 9,
    2: [[6, 6]] * 10,
    3: [[4, 7, 4]] * 10,
    4: [[n - n // 2, n // 2] for n in FAN],  # the centre aisle; an odd row puts its extra seat left of it
    5: [[5, 10, 5]] * 10,
    6: [[4, 8, 4]] * 2 + [[4, 14, 4]] * 8 + [[12]],
}
# CR-001 writes Grand as "A-B, C-J, K" counting the letter I; with I skipped (A.3: labels skip I) its eight
# middle rows are C-K and the recliner row is L. The counts (11 rows, 220 seats) are what bind.
RECLINER_ROW = "L"


def _rows(db, screen: int) -> list[tuple[str, int, list[int]]]:
    """(row_label, grid_row, sorted grid_cols) per row, front first."""
    return [(label, gr, sorted(cols)) for label, gr, cols in owner_sql(
        db, "SELECT seat.row_label, min(seat.grid_row), array_agg(seat.grid_col) FROM seat JOIN screen ON screen.id = seat.screen_id "
            "WHERE screen.name = %s GROUP BY 1 ORDER BY 2", (f"SCREEN {screen}",))]


def _blocks(cols: list[int], width: int) -> list[int]:
    """Seat counts of the runs of adjacent seats; a gap wider than one seat is an aisle."""
    out = [1]
    for a, b in zip(cols, cols[1:]):
        if b - a == width:
            out[-1] += 1
        else:
            out.append(1)
    return out


def test_each_hall_has_its_cr001_shape(seeded):
    db, _ = seeded
    for screen, want in HALLS.items():
        rows = _rows(db, screen)
        assert sum(map(sum, want)) == [90, 120, 150, 180, 200, 220][screen - 1]  # the table is self-consistent
        assert sum(len(c) for _, _, c in rows) == sum(map(sum, want)), screen
        # labels contiguous, skipping I; every row label sits on exactly one grid row
        assert "".join(label for label, _, _ in rows) == "ABCDEFGHJKLM"[:len(want)], screen
        assert len({gr for _, gr, _ in rows}) == len(want)
        wide = RECLINER_ROW if screen == 6 else None
        assert [_blocks(c, 2 if label == wide else 1) for label, _, c in rows] == want, screen
        # an aisle is exactly one empty column, and every row is centred on the widest row (within half a seat)
        widest = max(c[-1] + (2 if label == wide else 1) - 1 for label, _, c in rows)
        assert min(c[0] for _, _, c in rows) == 1, screen
        for label, _, c in rows:
            w = 2 if label == wide else 1
            left, right = c[0] - 1, widest - (c[-1] + w - 1)
            assert abs(left - right) <= 1, (screen, label, left, right)
            gaps = [b - a for a, b in zip(c, c[1:]) if b - a != w]
            assert gaps == [2] * (len(_blocks(c, w)) - 1), (screen, label, gaps)  # each aisle is one empty column
    # Stadium: rows A-D on grid rows 1-4, an empty walkway row 5, rows E-K on grid rows 6-11
    assert [gr for _, gr, _ in _rows(db, 5)] == [1, 2, 3, 4, 6, 7, 8, 9, 10, 11]
    # every other hall has no empty grid row
    for screen in (1, 2, 3, 4, 6):
        assert [gr for _, gr, _ in _rows(db, screen)] == list(range(1, len(HALLS[screen]) + 1)), screen
    # Fan: one centre aisle column shared by every row
    aisles = {next(a + 1 for a, b in zip(c, c[1:]) if b - a == 2) for _, _, c in _rows(db, 4)}
    assert len(aisles) == 1, aisles
    # Grand: the back row (L) is 12 recliners, each two columns wide, filling the hall's 24-column width
    k = next(c for label, _, c in _rows(db, 6) if label == RECLINER_ROW)
    assert k == list(range(1, 24, 2))
    assert owner_sql(db, "SELECT DISTINCT c.name FROM seat JOIN seat_category c ON c.id = seat.seat_category_id "
                         "JOIN screen ON screen.id = seat.screen_id WHERE screen.name = 'SCREEN 6' AND seat.row_label = 'L'") == [
        ("Recliner",)]
    # seat numbers run 1..n left to right inside each row, whatever the aisles
    assert owner_sql(db, "SELECT count(*) FROM (SELECT seat_number, row_number() OVER (PARTITION BY screen_id, row_label "
                         "ORDER BY grid_col) n FROM seat) x WHERE seat_number <> n") == [(0,)]


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

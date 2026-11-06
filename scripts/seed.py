"""FrontRow demonstration seed (PRD P-XCT-30, P-XCT-32; ledger S-XCT-44/45/46/48).

    python scripts/seed.py                    create what is missing, skip what exists
    python scripts/seed.py --wipe-and-reseed  LOCAL ONLY: empty every table, then seed

What it writes, all of it obviously demonstration data: DEMO CINEMA (Asia/Kolkata), six differently shaped
screens of 90..220 seats (CR-001 A.3), three seat categories, eleven DEMO lookup rows, four published DEMO MOVIE
films sharing one placeholder poster, each on its own fixed screen(s) (CR-001 A.2), 1 admin + 12 managers + 50
customers at SEED_EMAIL_DOMAIN, 720 showtimes centred on the injected clock's local date, and 11,003 captured
bookings at a deterministic occupancy. The figures a correct run must produce are docs/06 DataModel/seed/
expected_summary.json, except where CR-001 (hall shapes, films) and SRC-006 (the base price) have moved them and
that generated file has not yet been re-derived.

Rules this file keeps, each one an acceptance criterion:
- Idempotent, keyed on the ONE cinema row (whatever the admin has since renamed it to) and below it on the
  placeholder identifiers (names, emails, (screen, starts_at)). A run against a populated database inserts
  nothing and deletes nothing, and never resets a password changed by hand.
- ONE transaction: a failure part-way leaves the database exactly as it was - no partial catalogue. With
  --wipe-and-reseed the TRUNCATE is inside that same transaction, so a failed reseed un-wipes too.
- Write order: vocabulary, then screens and seats, then films, then showtimes (P-XCT-30 exception 7).
- No audit_log row. The seed creates the first admin itself, so no honest actor exists for its writes;
  this is the only exemption from the same-transaction audit rule (P-XCT-30 exception 10).
- One NOTICE line before the first showtime write, because that write freezes every hall's layout
  (P-ADM-14). A notice, never a prompt: this script must run as a one-off container task with no input.
- SEED_DEFAULT_PASSWORD from the environment only: validated before the first write, hashed ONCE with the
  application's own function, never printed, never written anywhere but users.password_hash.
- No receipt is enqueued: every seeded address is undeliverable, so each booking gets a receipt_dispatch
  row in state suppressed instead (P-TKT-04).

Time is injected: run() takes `now`; only main() asks the system clock.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# `app` is importable from the repository (backend/app) and from the image (/srv/app, with this file at
# /srv/scripts/seed.py). Without this the script only runs from one working directory.
for _root in (Path(__file__).resolve().parents[1] / "backend", Path(__file__).resolve().parents[1]):
    if (_root / "app").is_dir() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from app.core.config import Settings  # noqa: E402
from app.core.security import hash_password, password_problem  # noqa: E402
from app.domain import reference  # noqa: E402
from app.domain.pricing import seat_price_paise  # noqa: E402

# Set by run() from CINEMA_TIMEZONE (P-ADM-26 point 1, FR-ADR-067: the value the seed writes into the cinema row).
ZONE = ""
CINEMA_NAME = "DEMO CINEMA"


# (screen number, seats, rows front to back) - ASSUMED, OPEN-SCALE-02 / OPEN-SEAT-01 "you pick"; the approved plans,
# CR-003 (revision 5). Never a constraint. A row is (label, category S/P/R, ((x0, seats), ...) per block left to right),
# x0 the block's left edge in metres on the plan (0 = the hall's centre line, facing the screen); None is a walkway.
# Seats are 0.6 m wide, a Recliner 1.2 m; the grid column is the plan x on a 0.6 m grid, so an aisle is ~2 columns.
LAYOUT = [
    (1, 90, [  # Studio
        ("A", "S", ((-3.3, 11),)), ("B", "S", ((-3.6, 12),)), ("C", "S", ((-3.6, 12),)), ("D", "S", ((-3.6, 12),)),
        ("E", "P", ((-3.6, 12),)), ("F", "P", ((-3.6, 12),)), ("G", "P", ((-3.9, 13),)), ("H", "R", ((-3.6, 6),))]),
    (2, 120, [  # Centre aisle
        *[(r, "S", ((-3.575, 5), (0.575, 5))) for r in "ABC"], None, ("D", "S", ((-4.175, 6), (0.575, 6))),
        *[(r, "P", ((-4.175, 6), (0.575, 6))) for r in "EFGHJK"], ("L", "R", ((-4.175, 3), (0.575, 3)))]),
    (3, 150, [  # Twin aisle
        ("A", "S", ((-5.35, 3), (-2.4, 8), (3.55, 3))), ("B", "S", ((-5.95, 4), (-2.4, 8), (3.55, 4))), None,
        *[(r, "S", ((-5.95, 4), (-2.4, 8), (3.55, 4))) for r in "CD"],
        *[(r, "P", ((-5.95, 4), (-2.4, 8), (3.55, 4))) for r in "EFGHJ"], ("K", "R", ((-5.95, 2), (-2.4, 4), (3.55, 2)))]),
    (4, 180, [  # Fan
        ("A", "S", ((-4.75, 1), (-3, 10), (4.15, 1))), *[(r, "S", ((-5.35, 2), (-3, 10), (4.15, 2))) for r in "BC"],
        *[(r, "S", ((-5.95, 3), (-3, 10), (4.15, 3))) for r in "DE"], ("F", "S", ((-6.55, 4), (-3, 10), (4.15, 4))), None,
        ("G", "P", ((-6.55, 4), (-3, 10), (4.15, 4))), *[(r, "P", ((-7.15, 5), (-3, 10), (4.15, 5))) for r in "HJ"],
        ("K", "P", ((-7.15, 5), (-3, 10), (4.15, 6))), ("L", "R", ((-7.75, 3), (-3, 5), (4.15, 3)))]),
    (5, 200, [  # Stadium
        *[(r, "S", ((-4.775, 7), (0.575, 7))) for r in "ABCD"], None, ("E", "R", ((-7.75, 3), (-3, 5), (4.15, 3))),
        *[(r, "P", ((-5.95, 3), (-3, 10), (4.15, 3))) for r in "FGHJKL"],
        ("M", "P", ((-6.55, 4), (-3, 10), (4.15, 4))), ("N", "P", ((-6.55, 4), (-3, 10), (4.15, 5)))]),
    (6, 220, [  # Grand: stalls A-J, then the balcony K-N
        *[(r, "S", ((-5.95, 3), (-3, 10), (4.15, 3))) for r in "ABC"], None,
        *[(r, "S", ((-6.55, 4), (-3, 10), (4.15, 4))) for r in "DE"],
        *[(r, "P", ((-6.55, 4), (-3, 10), (4.15, 4))) for r in "FGH"], ("J", "R", ((-6.55, 2), (-3, 5), (4.15, 3))), None,
        *[(r, "P", ((-6.55, 4), (-3, 10), (4.15, 4))) for r in "KLMN"]]),
]
CAT_NAMES = {"S": "Standard", "P": "Premium", "R": "Recliner"}
SEAT_M, GRID_M = {"S": 0.6, "P": 0.6, "R": 1.2}, 0.6
# Row letters skip I (a seed habit only; SRC-004 R-4 permits I in the product).
ROW_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
# (name, uplift basis points) - ASSUMED, OPEN-SEAT-01 "you pick". The same three numbers as the pricing examples.
CATEGORIES = [("Standard", 0), ("Premium", 1250), ("Recliner", 3333)]
BASE_PRICE_PAISE = 1299  # ASSUMED seed value; integer minor unit - USD cents under SRC-006 (prices in US dollars)
LANGUAGES = ["DEMO LANGUAGE A", "DEMO LANGUAGE B", "DEMO LANGUAGE C"]
CERTIFICATIONS = ["DEMO RATING 1", "DEMO RATING 2"]
GENRES = ["DEMO GENRE 1", "DEMO GENRE 2", "DEMO GENRE 3", "DEMO GENRE 4"]
FORMATS = ["DEMO FORMAT 1", "DEMO FORMAT 2"]
FILMS = 4
# Per screen 1..6: (film index, minutes after SLOTS) - CR-001 A.2. Film 1 on Screens 6 and 5, Film 2 on 4 and 3,
# Film 3 on 2, Film 4 on 1; the second screen of a two-screen film starts 105 minutes later.
PROGRAMME = [(3, 0), (2, 0), (1, 105), (1, 0), (0, 105), (0, 0)]
DAYS = 30
SLOTS = [time(11, 0), time(14, 30), time(18, 0), time(21, 30)]  # ASSUMED local starts, 210 minutes apart
# The one placeholder poster, committed beside this file: a flat design-system shape (--fr-surface-inset),
# 400 x 600, no text. [JUDGMENT CALL] Phase 2 has no poster upload function (P-ADM-03 is Phase 6, and there
# is no local S3), so the seed records this fixed key and uploads nothing. Phase 6 replaces this with the
# admin upload path's own function; until then the poster redirect has no object behind this key.
POSTER_FILE = Path(__file__).resolve().parent / "assets" / "placeholder-poster.png"
POSTER_OBJECT_KEY = "posters/seed/placeholder-poster.png"
# The seed's own environment variables: read here and by nothing under backend/app (S7.9, S-XCT-48).
# .env.example lists exactly app/core/config.py's Settings plus these (S-XCT-29).
SEED_VARIABLES = ("SEED_DEFAULT_PASSWORD", "SEED_CHANGEOVER_MINUTES", "SEED_EMAIL_DOMAIN")
# The value .env.example ships on its SEED_DEFAULT_PASSWORD line. Refused by value.
PASSWORD_PLACEHOLDER = "CHANGE_ME_NOT_A_REAL_PASSWORD"
NOTICE = ("NOTICE: the next write freezes the seat layout of all six halls. Renumbering, removing or "
          "recategorising a seat is refused with 409 LAYOUT_FROZEN from now on.")
# Every table, children first, for the local-only wipe.
TABLES = ["admin_grant", "audit_log", "receipt_dispatch", "outbox_message", "idempotency_record", "booking_seat", "booking",
          "payment", "showtime_seat", "showtime", "movie_genre", "movie", "manager_screen_assignment",
          "password_reset_token", "seat", "screen", "seat_category", "cinema", "users", "language",
          "certification", "genre", "format"]


class SeedError(Exception):
    """The seed refuses: printed to stderr, exit 1, nothing written."""


def check_layout(layout) -> None:
    """The layout checked against itself before the first write (P-XCT-30 exception 9, CR-003): seat totals, a known
    category on every row, Standard first and at least one Recliner row, unique row labels skipping I."""
    for number, seats, plan in layout:
        name = f"SCREEN {number}"
        rows = [r for r in plan if r]
        counted = sum(n for _, _, blocks in rows for _, n in blocks)
        if counted != seats:
            raise SeedError(f"{name}: its rows hold {counted} seats, not {seats}")
        cats = [c for _, c, _ in rows]
        if set(cats) - set(CAT_NAMES) or cats[0] != "S" or "R" not in cats:
            raise SeedError(f"{name}: rows must be S/P/R, Standard nearest the screen, with a Recliner row")
        labels = [label for label, _, _ in rows]
        if len(set(labels)) != len(labels) or "I" in labels or not set(labels) <= set(ROW_LETTERS):
            raise SeedError(f"{name}: row labels {''.join(labels)} must be unique row letters")


class Db:
    """Every statement the seed runs goes through here, so a test can record the order (S-XCT-46)."""

    def __init__(self, conn, trace=None) -> None:
        self.conn, self.trace = conn, trace

    def _note(self, sql: str) -> None:
        if self.trace:
            self.trace(("sql", " ".join(sql.split())))

    def all(self, sql: str, params=None) -> list[tuple]:
        self._note(sql)
        cur = self.conn.execute(sql, params)
        return cur.fetchall() if cur.description else []

    def one(self, sql: str, params=None):
        rows = self.all(sql, params)
        return rows[0][0] if rows else None

    def many(self, sql: str, rows: list, returning: bool = False) -> list[tuple]:
        if not rows:
            return []
        self._note(sql)
        cur = self.conn.cursor()
        cur.executemany(sql, rows, returning=returning)
        out: list[tuple] = []
        if returning:
            while True:
                out.extend(cur.fetchall())
                if not cur.nextset():
                    break
        return out

    def copy(self, sql: str, rows) -> None:
        self._note(sql)
        with self.conn.cursor().copy(sql) as cp:
            for row in rows:
                cp.write_row(row)


def insert_vocabulary(db: Db) -> None:
    for table, names in (("language", LANGUAGES), ("certification", CERTIFICATIONS), ("genre", GENRES),
                         ("format", FORMATS)):
        db.many(f"INSERT INTO {table} (name, is_active) VALUES (%s, true) ON CONFLICT DO NOTHING", [(n,) for n in names])


def vocabulary(db: Db) -> dict[str, dict[str, int]]:
    """The eleven lookup rows by name. A missing one stops the seed before any film is written."""
    out: dict[str, dict[str, int]] = {}
    for table, names in (("language", LANGUAGES), ("certification", CERTIFICATIONS), ("genre", GENRES),
                         ("format", FORMATS)):
        found = dict(db.all(f"SELECT name, id FROM {table} WHERE name = ANY(%s)", (names,)))
        missing = [n for n in names if n not in found]
        if missing:
            raise SeedError(f"{table} rows {missing} do not exist; a film cannot be created without them (P-ADM-01)")
        out[table] = found
    return out


def ensure_cinema(db: Db, zone: str) -> tuple[int, str]:
    """The one cinema (SRC-003 C-2) and the zone the schedule is computed in. Keyed on the single row, never on
    its name: EP-ADM-29 lets the admin rename it, and a name key would then seed a second venue. An existing
    row's STORED timezone wins over CINEMA_TIMEZONE - it is the zone the existing schedule was written in."""
    rows = db.all("SELECT id, timezone FROM cinema ORDER BY id")
    if len(rows) > 1:
        raise SeedError(f"{len(rows)} cinema rows exist; the seed writes one venue and will not guess which to fill")
    if rows:
        return rows[0][0], rows[0][1]
    return db.one("INSERT INTO cinema (name, timezone, version) VALUES (%s, %s, 1) RETURNING id", (CINEMA_NAME, zone)), zone


def insert_halls(db: Db, cinema_id: int) -> tuple[list[int], dict[str, int]]:
    """The categories, the six screens and their seats. Returns screen ids by number and category ids."""
    db.many("INSERT INTO seat_category (name, uplift_basis_points, version) VALUES (%s, %s, 1) ON CONFLICT DO NOTHING",
            CATEGORIES)
    categories = dict(db.all("SELECT name, id FROM seat_category WHERE name = ANY(%s)", ([n for n, _ in CATEGORIES],)))
    screen_ids = []
    for number, _seats, plan in LAYOUT:
        name = f"SCREEN {number}"
        sid = db.one("SELECT id FROM screen WHERE cinema_id = %s AND name = %s", (cinema_id, name))
        if sid is None:
            sid = db.one("INSERT INTO screen (cinema_id, name, is_active, version) VALUES (%s, %s, true, 1) RETURNING id",
                         (cinema_id, name))
        screen_ids.append(sid)
        left = min(x0 for row in plan if row for x0, _ in row[2])
        seats = []
        for grid_row, row in enumerate(plan, 1):
            if not row:
                continue  # a walkway (or the balcony's front): an empty grid row, no row letter used
            label, cat, blocks = row
            n = 1
            for x0, count in blocks:
                for i in range(count):
                    col = 1 + int((x0 + i * SEAT_M[cat] - left) / GRID_M + 0.5 + 1e-6)  # plan x on the 0.6 m grid, half up (round() is half-even; 1e-6 for float noise)
                    seats.append((sid, label, n, grid_row, col, categories[CAT_NAMES[cat]]))
                    n += 1
        db.many("INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id, is_active) "
                "VALUES (%s, %s, %s, %s, %s, %s, true) ON CONFLICT DO NOTHING", seats)
    return screen_ids, categories


def anchor_day(db: Db, now: datetime, screen_ids: list[int]):
    """The local date of day index 0: the earliest existing SEEDED showtime's (on the six seeded halls, at a
    seeded slot), else the clock's minus 15 (P-XCT-30 'The showtime's placeholder identity'). A re-run therefore
    recomputes the identical schedule; a showtime the admin added on another hall or at another time is not
    an anchor."""
    zone = ZoneInfo(ZONE)
    for (starts_at,) in db.all("SELECT starts_at FROM showtime WHERE screen_id = ANY(%s) ORDER BY starts_at", (screen_ids,)):
        if starts_at.astimezone(zone).time() in SLOTS:
            return starts_at.astimezone(zone).date()
    if db.one("SELECT count(*) FROM showtime WHERE screen_id = ANY(%s)", (screen_ids,)):
        # Showtimes exist on the seeded halls but none sits at a seeded local slot: the cinema's timezone was
        # changed after the seed ran. Recomputing would write a second, shifted schedule over the first.
        raise SeedError(f"the seeded halls hold showtimes, but none starts at a seeded time in {ZONE}; the cinema's "
                        "timezone has changed since the seed ran, and a re-run would write a second schedule")
    return now.astimezone(zone).date() - timedelta(days=15)


def local(day, at: time) -> datetime:
    return datetime.combine(day, at, tzinfo=ZoneInfo(ZONE))


def insert_films(db: Db, vocab, first_day, now: datetime) -> list[int]:
    """DEMO MOVIE 01..04, published from the injected clock, inside a window covering the whole schedule."""
    display_from, display_until = local(first_day, time(0)), local(first_day + timedelta(days=DAYS), time(0))
    ids = []
    for i in range(FILMS):
        title = f"DEMO MOVIE {i + 1:02d}"
        mid = db.one("SELECT min(id) FROM movie WHERE title = %s", (title,))
        if mid is None:
            mid = db.one(
                "INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, poster_object_key, "
                "published_at, display_from, display_until, version) VALUES (%s, '', %s, %s, %s, %s, %s, %s, %s, 1) RETURNING id",
                (title, 90 + i * 10, vocab["certification"][CERTIFICATIONS[i % 2]], vocab["language"][LANGUAGES[i % 3]],
                 POSTER_OBJECT_KEY, now, display_from, display_until))
        ids.append(mid)
        db.many("INSERT INTO movie_genre (movie_id, genre_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                [(mid, vocab["genre"][GENRES[i % 4]]), (mid, vocab["genre"][GENRES[(i + 1) % 4]])])
    return ids


def accounts(domain: str) -> list[tuple[str, str]]:
    return ([(f"admin-01@{domain}", "admin")] + [(f"manager-{m:02d}@{domain}", "manager") for m in range(1, 13)]
            + [(f"customer-{c:02d}@{domain}", "customer") for c in range(1, 51)])


def insert_accounts(db: Db, domain: str, password: str, cost: int, hasher) -> dict[str, int]:
    """63 accounts, one bcrypt run for all of them, and only if one is missing. Existing accounts are
    skipped, so a password changed by hand is never reset (P-XCT-32 exception 8)."""
    wanted = accounts(domain)
    existing = dict(db.all("SELECT lower(email), id FROM users WHERE lower(email) = ANY(%s)", ([e for e, _ in wanted],)))
    missing = [(e, r) for e, r in wanted if e not in existing]
    if missing:
        password_hash = hasher(password, cost)
        db.many("INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, %s, 1) "
                "ON CONFLICT DO NOTHING", [(e, password_hash, r) for e, r in missing])
    return dict(db.all("SELECT lower(email), id FROM users WHERE lower(email) = ANY(%s)", ([e for e, _ in wanted],)))


def assign_managers(db: Db, users: dict[str, int], domain: str, screen_ids: list[int]) -> None:
    # screen_number = floor((m - 1) / 2) + 1 (P-XCT-30, PROVISIONAL with SRC-003 C-1)
    db.many("INSERT INTO manager_screen_assignment (user_id, screen_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [(users[f"manager-{m:02d}@{domain}"], screen_ids[(m - 1) // 2]) for m in range(1, 13)])


def schedule(first_day, screen_ids, film_ids, runtimes, format_ids, padding_minutes: int):
    """The 720 showtimes in ascending (day, slot, screen) order, k = 0..719."""
    k = 0
    for d in range(DAYS):
        for slot, at in enumerate(SLOTS):
            for screen_index, sid in enumerate(screen_ids):
                film, offset = PROGRAMME[screen_index]
                starts = local(first_day + timedelta(days=d), at) + timedelta(minutes=offset)
                yield {"k": k, "screen_index": screen_index, "screen_id": sid, "movie_id": film_ids[film],
                       "starts_at": starts, "ends_at": starts + timedelta(minutes=runtimes[film] + padding_minutes),
                       "format_id": format_ids[(d * len(SLOTS) + slot) % 2]}
                k += 1


def insert_showtimes(db: Db, plan: list[dict], out) -> list[dict]:
    """Insert the planned showtimes that do not exist yet, keyed on (screen_id, starts_at). Returns the new ones."""
    existing = {(s, t) for s, t in db.all("SELECT screen_id, starts_at FROM showtime WHERE screen_id = ANY(%s)",
                                          (list({p["screen_id"] for p in plan}),))}
    new = [p for p in plan if (p["screen_id"], p["starts_at"]) not in existing]
    if not new:
        return []
    seat_count = dict(db.all("SELECT screen_id, count(*) FROM seat WHERE is_active AND screen_id = ANY(%s) GROUP BY 1",
                             (list({p["screen_id"] for p in new}),)))
    out(NOTICE)  # before the first showtime write, exactly once
    ids = db.many("INSERT INTO showtime (movie_id, screen_id, starts_at, ends_at, base_price_paise, format_id, "
                  "seat_count_at_creation, version) VALUES (%s, %s, %s, %s, %s, %s, %s, 1) RETURNING id",
                  [(p["movie_id"], p["screen_id"], p["starts_at"], p["ends_at"], BASE_PRICE_PAISE, p["format_id"],
                    seat_count[p["screen_id"]]) for p in new], returning=True)
    for p, (sid,) in zip(new, ids):
        p["showtime_id"] = sid
    # The materialised seat set, one row per in-service seat (P-ADM-14).
    db.all("INSERT INTO showtime_seat (showtime_id, seat_id) SELECT s.id, seat.id FROM showtime s "
           "JOIN seat ON seat.screen_id = s.screen_id AND seat.is_active WHERE s.id = ANY(%s)",
           ([p["showtime_id"] for p in new],))
    return new


def insert_bookings(db: Db, plan: list[dict], new: list[dict], customers: list[int], first_day) -> None:
    """occupancy = 10 + (k mod 9) * 10 percent, taken from row A seat 1 onward; booking_size =
    min(1 + (booking_index mod 10), seats remaining); owner = customer[booking_index mod 50]. booking_index
    is global over all 720 showtimes, so it is advanced for showtimes that already exist too."""
    new_ids = {p["k"]: p["showtime_id"] for p in new}
    seats_by_screen: dict[int, list[tuple[int, int, int]]] = {}
    for sid, seat_id, cat, uplift in db.all(
            "SELECT s.screen_id, s.id, s.seat_category_id, c.uplift_basis_points FROM seat s "
            "JOIN seat_category c ON c.id = s.seat_category_id WHERE s.is_active AND s.screen_id = ANY(%s) "
            "ORDER BY s.screen_id, s.grid_row, s.grid_col", (list({p["screen_id"] for p in plan}),)):
        seats_by_screen.setdefault(sid, []).append((seat_id, cat, uplift))
    # [JUDGMENT CALL] every seeded booking and payment is dated at local midnight of day index 0: before every
    # seeded showtime, and never after the clock that seeded it (the column default would date a booking on a
    # past show after the show - expected_summary.json 'unspecified').
    booked_at = local(first_day, time(0))
    used = {r for (r,) in db.all("SELECT reference FROM booking")}
    bookings = []  # (showtime_id, owner, [(seat_id, cat, uplift, price)])
    booking_index = 0
    for p in plan:
        seats = seats_by_screen[p["screen_id"]]
        taken = len(seats) * (10 + (p["k"] % 9) * 10) // 100
        cursor = 0
        while cursor < taken:
            size = min(1 + booking_index % 10, taken - cursor)
            if p["k"] in new_ids:
                lines = [(s, c, u, seat_price_paise(BASE_PRICE_PAISE, u)) for s, c, u in seats[cursor:cursor + size]]
                bookings.append((new_ids[p["k"]], customers[booking_index % 50], lines))
            cursor += size
            booking_index += 1
    if not bookings:
        return
    refs = []
    for _ in bookings:
        ref = reference.new_reference()
        while ref in used:
            ref = reference.new_reference()
        used.add(ref)
        refs.append(ref)
    totals = [sum(line[3] for line in lines) for _, _, lines in bookings]
    # [JUDGMENT CALL] payment.idempotency_key is NOT NULL and no document says what the seed writes:
    # 'seed-' + the booking reference - unique, obviously seeded, and never a customer's key.
    payment_ids = db.many(
        "INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at, created_at) "
        "VALUES ('captured', %s, %s, %s, %s, %s, %s) RETURNING id",
        [(t, f"seed-{r}", booked_at, booked_at, booked_at, booked_at) for t, r in zip(totals, refs)], returning=True)
    booking_ids = db.many(
        "INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, 'confirmed', %s) RETURNING id",
        [(r, owner, st, pid, t, booked_at) for r, (st, owner, _), (pid,), t in zip(refs, bookings, payment_ids, totals)],
        returning=True)
    db.copy("COPY booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
            "uplift_basis_points_applied, seat_category_id, created_at) FROM STDIN",
            ((bid, st, s, price, BASE_PRICE_PAISE, u, c, booked_at)
             for (bid,), (st, _, lines) in zip(booking_ids, bookings) for s, c, u, price in lines))
    # One dispatch row per booking, suppressed: no send was attempted and none ever will be (P-TKT-04).
    db.copy("COPY receipt_dispatch (booking_id, status, dispatch_seq, attempts) FROM STDIN",
            ((bid, "suppressed", 1, 0) for (bid,) in booking_ids))


def run(conn, *, password: str, cost: int, domain: str, padding_minutes: int, now: datetime, out=print,
        hasher=hash_password, trace=None, zone: str, wipe_first: bool = False) -> None:
    """The whole seed in ONE transaction on `conn` (a psycopg connection) - the local-only wipe included."""
    global ZONE
    check_layout(LAYOUT)
    if not POSTER_FILE.is_file():
        raise SeedError(f"the placeholder poster {POSTER_FILE.name} is missing beside this script")
    db = Db(conn, trace)
    with conn.transaction():
        if wipe_first:
            wipe(db)
        insert_vocabulary(db)
        cinema_id, ZONE = ensure_cinema(db, zone)
        screen_ids, _ = insert_halls(db, cinema_id)
        vocab = vocabulary(db)
        first_day = anchor_day(db, now, screen_ids)
        film_ids = insert_films(db, vocab, first_day, now)
        users = insert_accounts(db, domain, password, cost, hasher)
        assign_managers(db, users, domain, screen_ids)
        runtimes = [90 + i * 10 for i in range(FILMS)]
        plan = list(schedule(first_day, screen_ids, film_ids, runtimes,
                             [vocab["format"][f] for f in FORMATS], padding_minutes))
        new = insert_showtimes(db, plan, out)
        insert_bookings(db, plan, new, [users[f"customer-{c:02d}@{domain}"] for c in range(1, 51)], first_day)
    for role, n in (("admin", 1), ("manager", 12), ("customer", 50)):
        out(f"{role}: {n}")
        for email, r in accounts(domain):
            if r == role:
                out(f"  {email}")


def wipe(db: Db) -> None:
    """LOCAL ONLY. Needs the owner's credentials (the application role holds no TRUNCATE). Called inside run()'s
    transaction, never on its own: TRUNCATE is transactional in PostgreSQL, so a reseed that fails rolls it back."""
    db.all("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY")


def seed_inputs() -> dict:
    """Everything the seed reads from the environment, validated before the first write."""
    # The seed reads its own three variables here and nowhere else (S7.9: "read by the seed and by nothing
    # else"), so no API or worker container is made to refuse to boot over a value it has no use for.
    env = os.environ
    password = env.get("SEED_DEFAULT_PASSWORD") or ""  # set-but-empty is absent
    if not password:
        raise SeedError("SEED_DEFAULT_PASSWORD is required and is not set (or is empty). Nothing was written.")
    if password == PASSWORD_PLACEHOLDER:  # by value, not by pattern
        raise SeedError("SEED_DEFAULT_PASSWORD is still the .env.example placeholder; set a real one. Nothing was written.")
    defaults = Settings.model_fields  # the application's own defaults, never a second copy
    try:
        cost = int(env.get("BCRYPT_COST") or defaults["BCRYPT_COST"].default)
        min_length = int(env.get("PASSWORD_MIN_LENGTH") or defaults["PASSWORD_MIN_LENGTH"].default)
        padding_minutes = int(env.get("SEED_CHANGEOVER_MINUTES") or 20)  # ASSUMED; not an answer to PROPOSED-TURNAROUND-01
    except ValueError:
        raise SeedError("BCRYPT_COST, PASSWORD_MIN_LENGTH and SEED_CHANGEOVER_MINUTES must be whole numbers") from None
    if not 0 <= padding_minutes <= 50:
        # Over 50 the longest film plus this padding overruns the 210-minute slot spacing.
        raise SeedError("SEED_CHANGEOVER_MINUTES must be between 0 and 50")
    # The registration path's own rule: the floor in CHARACTERS, the ceiling in BYTES (bcrypt reads 72).
    problem = password_problem(password, min_length)
    if problem:
        raise SeedError(f"SEED_DEFAULT_PASSWORD is refused: {problem} "
                        f"(the bounds are PASSWORD_MIN_LENGTH = {min_length} characters and 72 bytes). Nothing was written.")
    url = env.get("DATABASE_URL")
    if not url:
        raise SeedError("DATABASE_URL is required and is not set. Nothing was written.")
    domain = env.get("SEED_EMAIL_DOMAIN") or "demo.frontrow.invalid"  # RFC 2606: never resolves
    zone = env.get("CINEMA_TIMEZONE") or defaults["CINEMA_TIMEZONE"].default
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise SeedError(f"CINEMA_TIMEZONE {zone!r} is not an IANA zone name. Nothing was written.") from None
    return {"password": password, "cost": cost, "domain": domain, "padding_minutes": padding_minutes, "url": url, "zone": zone}


def main(argv=None, *, now: datetime | None = None, connect=None, out=print, hasher=hash_password,
         trace=None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed.py", description="Create FrontRow's demonstration data. Idempotent: what exists is skipped.")
    parser.add_argument("--wipe-and-reseed", action="store_true",
                        help="LOCAL ONLY. Empty every table, then seed. Never run against the deployed environment: "
                             "seeded rows there are permanent. Needs the owner's DATABASE_URL.")
    args = parser.parse_args(argv)
    try:
        inputs = seed_inputs()
    except SeedError as exc:
        print(f"seed: {exc}", file=sys.stderr)
        return 78  # EX_CONFIG, the same code the API exits with on a bad configuration
    if now is None:
        from app.core.clock import SystemClock
        now = SystemClock().now()
    if connect is None:
        import psycopg
        connect = psycopg.connect
    try:
        with connect(inputs.pop("url")) as conn:
            run(conn, now=now, out=out, hasher=hasher, trace=trace, wipe_first=args.wipe_and_reseed, **inputs)
    except SeedError as exc:
        print(f"seed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

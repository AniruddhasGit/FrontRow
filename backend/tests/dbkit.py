"""Database fixtures and helpers for every lane's tests (Phase 2).

Every database test runs against a THROWAWAY database created for its test module on the compose
postgres, bootstrapped with docs/06 DataModel/checks/roles_local.sql verbatim and migrated with the
real `migrate` command of the container entrypoint, then dropped. Run with:

    docker compose --profile test run --rm --build test

One database per test MODULE, so modules never share rows; never one shared database (GOTCHAS:
parallel suites against one database deadlock on per-test cleanup). The `frontrow` database is never
touched. These helpers FAIL, never skip, when the environment is missing: a skipped database test is
a check that silently did not run.

Use: `migrated_db` (module fixture, re-exported by conftest.py) gives a TestDatabase with three URLs.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
# A syntactically valid bcrypt string that no password produces. Fixture rows only.
FAKE_HASH = "$2b$" + "04$" + "x" * 53  # split, so no bcrypt-shaped literal is committed (S-XCT-48)


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    return value


def datamodel_dir() -> Path:
    return Path(_env("DATAMODEL_DIR"))


def _url(base: str, user: str, password: str, dbname: str) -> str:
    parts = urlsplit(base)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit(("postgresql", f"{user}:{password}@{host}", f"/{dbname}", "", ""))


@dataclass(frozen=True)
class TestDatabase:
    __test__ = False  # not a test class, despite the name
    name: str
    admin_url: str  # superuser, this database - bootstrap and teardown only
    owner_url: str  # frontrow_owner - what `migrate` connects as
    app_url: str  # frontrow_app - what the API connects as


def create_database(*, migrate: bool) -> TestDatabase:
    import psycopg
    from psycopg import sql

    admin = _env("TEST_ADMIN_DATABASE_URL")
    name = "fr_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    a = urlsplit(admin)
    db = TestDatabase(
        name=name,
        admin_url=_url(admin, a.username, a.password, name),
        owner_url=_url(admin, "frontrow_owner", _env("TEST_OWNER_PASSWORD"), name),
        app_url=_url(admin, "frontrow_app", _env("TEST_APP_PASSWORD"), name),
    )
    # The operator's step, verbatim from the file of record: roles, CONNECT, schema privileges.
    run_psql(db.admin_url, "-v", f"owner_password={_env('TEST_OWNER_PASSWORD')}", "-v",
             f"app_password={_env('TEST_APP_PASSWORD')}", "-f", str(datamodel_dir() / "checks" / "roles_local.sql"), check=True)
    if migrate:
        result = run_migrate(db.owner_url)
        assert result.returncode == 0, result.stdout + result.stderr
    return db


def run_psql(url: str, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", url, *args], capture_output=True, text=True, timeout=120)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def run_migrate(database_url: str) -> subprocess.CompletedProcess:
    """The real `migrate` command of the container entrypoint, exactly as the one-off task runs it."""
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(["sh", "entrypoint.sh", "migrate"], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120)


def drop_database(db: TestDatabase) -> None:
    import psycopg
    from psycopg import sql

    with psycopg.connect(_env("TEST_ADMIN_DATABASE_URL"), autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(db.name)))


@pytest.fixture(scope="module")
def migrated_db():
    db = create_database(migrate=True)
    yield db
    try:
        # S-ADM-02: "SELECT count(*) FROM audit_log WHERE actor_user_id IS NULL returns 0 after the whole suite has run".
        # Every module has its own database, so the suite's audit rows are the union of these; each is checked last.
        assert owner_sql(db, "SELECT count(*) FROM audit_log WHERE actor_user_id IS NULL") == [(0,)]
    finally:
        drop_database(db)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def app_settings(db: TestDatabase, **overrides: str):
    from app.core.config import Settings

    from .conftest import VALID_ENV

    return Settings(**{**VALID_ENV, "DATABASE_URL": db.app_url, **overrides})


def run_sql(url: str, statement: str, params: tuple | dict | None = None) -> list[tuple]:
    """One statement, autocommitted, as whichever role the URL names. Returns any rows."""
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        cur = conn.execute(statement, params)
        return cur.fetchall() if cur.description else []


def owner_sql(db: TestDatabase, statement: str, params: tuple | dict | None = None) -> list[tuple]:
    return run_sql(db.owner_url, statement, params)


def app_sql(db: TestDatabase, statement: str, params: tuple | dict | None = None) -> list[tuple]:
    return run_sql(db.app_url, statement, params)


def insert_user(db: TestDatabase, *, role: str, email: str | None = None, user_id: int | None = None,
                password_hash: str = FAKE_HASH) -> int:
    email = email or f"{uuid.uuid4().hex[:10]}@example.invalid"
    if user_id is None:
        return owner_sql(db, "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, %s, 1) RETURNING id",
                         (email, password_hash, role))[0][0]
    return owner_sql(db, "INSERT INTO users (id, email, password_hash, role, password_version) OVERRIDING SYSTEM VALUE "
                         "VALUES (%s, %s, %s, %s, 1) RETURNING id", (user_id, email, password_hash, role))[0][0]


def insert_showtime(db: TestDatabase, *, showtime_id: int | None = None, base_price_paise: int = 25000) -> dict:
    """The minimum chain of rows a showtime needs (venue -> hall -> one seat, a film).
    Demonstration values only - the seed's ASSUMED names never enter a test (OPEN-SEAT-01)."""
    tag = uuid.uuid4().hex[:8]
    one = lambda q, p: owner_sql(db, q, p)[0][0]  # noqa: E731
    cinema = one("INSERT INTO cinema (name, timezone, version) VALUES (%s, 'Asia/Kolkata', 1) RETURNING id", (f"Venue {tag}",))
    screen = one("INSERT INTO screen (cinema_id, name, version) VALUES (%s, %s, 1) RETURNING id", (cinema, f"Hall {tag}"))
    category = one("INSERT INTO seat_category (name, uplift_basis_points, version) VALUES (%s, 0, 1) RETURNING id", (f"Cat {tag}",))
    seat = one("INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
               "VALUES (%s, 'C', 12, 3, 12, %s) RETURNING id", (screen, category))
    cert = one("INSERT INTO certification (name, is_active) VALUES (%s, true) RETURNING id", (f"Cert {tag}",))
    lang = one("INSERT INTO language (name, is_active) VALUES (%s, true) RETURNING id", (f"Lang {tag}",))
    movie = one("INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, version) "
                "VALUES (%s, 'Demonstration film.', 120, %s, %s, 1) RETURNING id", (f"DEMO {tag}", cert, lang))
    cols = "movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version"
    vals = "%s, %s, '2026-09-01T18:00:00+05:30', '2026-09-01T20:30:00+05:30', %s, 1, 1"
    if showtime_id is None:
        st = one(f"INSERT INTO showtime ({cols}) VALUES ({vals}) RETURNING id", (movie, screen, base_price_paise))
    else:
        st = one(f"INSERT INTO showtime (id, {cols}) OVERRIDING SYSTEM VALUE VALUES (%s, {vals}) RETURNING id",
                 (showtime_id, movie, screen, base_price_paise))
    owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (%s, %s)", (st, seat))
    return {"showtime_id": st, "seat_id": seat, "seat_category_id": category, "screen_id": screen}


def insert_booking(db: TestDatabase, *, user_id: int, showtime: dict, price_paise: int, reference: str) -> int:
    """One captured payment, one booking, one booked seat - in ONE transaction, so a refused seat
    (the guard working) leaves no orphan booking behind."""
    import psycopg

    with psycopg.connect(db.owner_url) as conn, conn.transaction():
        payment = conn.execute(
            "INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at) "
            "VALUES ('captured', %s, %s, '2026-08-12T18:41:00Z', '2026-08-12T18:41:01Z', '2026-08-12T18:41:02Z') RETURNING id",
            (price_paise, uuid.uuid4().hex)).fetchone()[0]
        booking = conn.execute(
            "INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) "
            "VALUES (%s, %s, %s, %s, %s, 'confirmed') RETURNING id",
            (reference, user_id, showtime["showtime_id"], payment, price_paise)).fetchone()[0]
        conn.execute(
            "INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
            "uplift_basis_points_applied, seat_category_id) VALUES (%s, %s, %s, %s, %s, 0, %s)",
            (booking, showtime["showtime_id"], showtime["seat_id"], price_paise, price_paise, showtime["seat_category_id"]))
    return booking

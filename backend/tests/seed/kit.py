"""Shared helpers for the seed tests (S-XCT-43..49, S-SCP-05): load scripts/seed.py, run it in-process against
a throwaway migrated database, and read docs/06 DataModel/seed/expected_summary.json as the oracle.

The seed runs as frontrow_app (the application role), so a missing grant shows up here and not on RDS.
Time is injected: every in-process run passes NOW; nothing here reads the wall clock.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from tests.dbkit import create_database, drop_database, owner_sql
from tests.xct._support import REPO

SEED_PATH = REPO / "scripts" / "seed.py"
SUMMARY = json.loads((REPO / "docs" / "06 DataModel" / "seed" / "expected_summary.json").read_text(encoding="utf-8"))
# The injected clock: 09:30 UTC = 15:00 Asia/Kolkata, so "today" is unambiguous in both zones.
NOW = datetime(2026, 10, 18, 9, 30, tzinfo=timezone.utc)
# A test-only value. Not a credential: it exists only inside throwaway databases dropped after each module.
PASSWORD = "seed-test-password-only"
DOMAIN = "demo.frontrow.invalid"


def load_seed():
    spec = importlib.util.spec_from_file_location("frontrow_seed", SEED_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = load_seed()


@contextmanager
def seed_env(**values: str | None):
    """The environment for one seed run; every SEED_ variable and the two bounds cleared first."""
    names = ["SEED_DEFAULT_PASSWORD", "SEED_EMAIL_DOMAIN", "SEED_CHANGEOVER_MINUTES", "BCRYPT_COST",
             "PASSWORD_MIN_LENGTH", "DATABASE_URL", *values]
    saved = {n: os.environ.get(n) for n in names}
    try:
        for n in names:
            os.environ.pop(n, None)
        for n, v in values.items():
            if v is not None:
                os.environ[n] = v
        yield
    finally:
        for n, v in saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v


def run_seed(db_url: str, *argv: str, password: str | None = PASSWORD, now: datetime = NOW, **kwargs) -> tuple[int, list[str]]:
    """seed.main() in-process. Returns the exit code and the stdout lines it printed."""
    lines: list[str] = []
    out = kwargs.pop("out", lines.append)
    with seed_env(DATABASE_URL=db_url, SEED_DEFAULT_PASSWORD=password, BCRYPT_COST="4"):
        code = seed.main(list(argv), now=now, out=out, **kwargs)
    return code, lines


def run_seed_process(db_url: str | None, *argv: str, password: str | None = PASSWORD) -> subprocess.CompletedProcess:
    """`python scripts/seed.py` as a separate process with stdin CLOSED, the way a one-off container task runs it.
    Only used for runs whose assertions cannot depend on the date (validation failures, --help, row counts)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SEED_")}
    env.pop("DATABASE_URL", None)
    env["BCRYPT_COST"] = "4"
    if db_url:
        env["DATABASE_URL"] = db_url
    if password is not None:
        env["SEED_DEFAULT_PASSWORD"] = password
    return subprocess.run([sys.executable, str(SEED_PATH), *argv], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=600)


def table_counts(db) -> dict[str, int]:
    tables = [t for (t,) in owner_sql(db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                                          "AND table_type = 'BASE TABLE' AND table_name <> 'alembic_version' ORDER BY 1")]
    assert len(tables) == 22, tables  # a vacuous comparison is not a comparison
    return {t: owner_sql(db, f"SELECT count(*) FROM {t}")[0][0] for t in tables}


def one(db, statement: str, params=None):
    return owner_sql(db, statement, params)[0][0]


@pytest.fixture(scope="module")
def seeded():
    """A throwaway migrated database seeded once, as frontrow_app, at the injected clock. Yields (db, stdout lines)."""
    db = create_database(migrate=True)
    try:
        code, lines = run_seed(db.app_url)
        assert code == 0, lines
        yield db, lines
    finally:
        drop_database(db)


@pytest.fixture(scope="module")
def empty_db():
    db = create_database(migrate=True)
    yield db
    drop_database(db)

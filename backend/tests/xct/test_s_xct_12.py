"""S-XCT-12 - credentials are stored so they cannot be read back.

Covered: the length rules (characters for the floor, BYTES for the ceiling), bcrypt confined to
core/security.py and never inside an `async def`, the dummy-hash comparison for an unknown email, the
lower(email) unique index, the email stored as entered, and no plaintext column. NOT covered: the
registration / sign-in HTTP responses (422 / 409 / 401, email 254/255) and `to_thread.run_sync` in
the auth router - the account lane's EP-ACC-01/02.
"""

from __future__ import annotations

import re

import bcrypt as bcrypt_lib
import psycopg
import pytest

from app.core import security
from app.core.security import hash_password, password_problem, verify_password
from tests.dbkit import BACKEND_DIR, app_sql

COST = 4  # bcrypt's minimum, for test speed; production default is BCRYPT_COST=12


def test_eleven_characters_is_refused_with_the_floor_message():
    assert password_problem("a" * 11, 12) == "Use a password of at least 12 characters."
    assert password_problem("a" * 12, 12) is None


def test_the_floor_counts_characters_not_bytes():
    assert password_problem("क" * 12, 12) is None  # 12 characters, 36 bytes


def test_seventy_five_bytes_of_devanagari_is_refused_and_not_truncated():
    password = "क" * 25
    assert len(password) == 25 and len(password.encode("utf-8")) == 75
    assert password_problem(password, 12) == "Use a password of 72 bytes or fewer. Some characters count as more than one byte."


def test_seventy_two_latin_characters_are_accepted_and_round_trip():
    password = "L" * 72
    assert password_problem(password, 12) is None
    stored = hash_password(password, COST)
    assert verify_password(password, stored, COST)
    assert not verify_password("L" * 71 + "M", stored, COST)


def test_the_stored_hash_is_bcrypt_and_never_the_plaintext():
    stored = hash_password("Correct-Horse-99!", COST)
    assert stored.startswith("$2b$") and "Correct-Horse-99!" not in stored


def test_an_unknown_email_still_runs_exactly_one_bcrypt_comparison_against_a_dummy_hash(monkeypatch):
    calls = []
    real = bcrypt_lib.checkpw

    def counting(pw, hashed):
        calls.append(hashed)
        return real(pw, hashed)

    monkeypatch.setattr(security.bcrypt, "checkpw", counting)
    known = hash_password("Correct-Horse-99!", COST)
    calls.clear()
    assert verify_password("Correct-Horse-99!", known, COST) is True
    assert verify_password("Correct-Horse-99!", None, COST) is False  # unknown email
    assert len(calls) == 2 and calls[0] != calls[1]  # one comparison each; the second against the dummy


def test_bcrypt_is_called_only_in_security_py_and_security_py_has_no_async_def():
    rx = re.compile(r"bcrypt\.(hashpw|checkpw|gensalt)")
    hits = [str(p) for p in (BACKEND_DIR / "app").rglob("*.py") if p.name != "security.py" and rx.search(p.read_text(encoding="utf-8"))]
    assert hits == []
    assert "async def" not in (BACKEND_DIR / "app" / "core" / "security.py").read_text(encoding="utf-8")


def test_a_unique_index_exists_on_lower_email(migrated_db):
    defs = [r[0] for r in app_sql(migrated_db, "SELECT indexdef FROM pg_indexes WHERE tablename = 'users'")]
    unique_lower = [d for d in defs if d.startswith("CREATE UNIQUE INDEX") and "lower(email)" in d]
    assert len(unique_lower) == 1, defs


def test_the_email_is_stored_as_entered_and_unique_case_insensitively(migrated_db):
    insert = "INSERT INTO users (email, password_hash, role, password_version) VALUES (%s, %s, 'customer', 1) RETURNING id"
    stored = hash_password("Correct-Horse-99!", COST)
    (user_id,) = app_sql(migrated_db, insert, ("Nikhil@Example.invalid", stored))[0]
    assert app_sql(migrated_db, "SELECT email FROM users WHERE id = %s", (user_id,)) == [("Nikhil@Example.invalid",)]
    with pytest.raises(psycopg.errors.UniqueViolation):
        app_sql(migrated_db, insert, ("nikhil@example.INVALID", stored))


def test_no_plaintext_password_column_exists(migrated_db):
    assert app_sql(migrated_db, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                                "AND table_name = 'users' AND column_name IN ('password', 'password_plain')") == []

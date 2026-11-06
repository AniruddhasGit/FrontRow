"""S-XCT-12 - credentials are stored so they cannot be read back.

Every clause runs as the cell states it. Over HTTP (EP-ACC-01/02): 11 characters -> 422 with the floor
sentence, 25 Devanagari characters (75 bytes) -> 422 quoting 75 and nothing stored, 72 Latin characters
-> 201, a second registration -> 409 EMAIL_ALREADY_REGISTERED, a wrong password or unknown email at
sign-in -> 401 CREDENTIALS_INVALID, Nikhil@Example.invalid read back unchanged, a 255-character email ->
422 and a 254-character one -> 201, and Correct-Horse-99! in no captured stdout line (DEBUG) and no
response body. The rg sweeps (bcrypt outside security.py, no async def in it, to_thread.run_sync over
api/auth.py + domain/accounts >= 1) and the catalogue checks run on the source and the database.
password_problem() is the seed's check (scripts/seed.py), tested here too.
"""

from __future__ import annotations

import re

import bcrypt as bcrypt_lib
import psycopg
import pytest

from app.core import security
from app.core.security import hash_password, password_problem, verify_password
from tests.acc._support import api, flush_redis, settings_for
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


def _email(length: int) -> str:
    domain = "a" * 63 + "." + "b" * 63 + "."
    local = "x" * 64
    tail = ".com"
    middle = length - len(local) - 1 - len(domain) - len(tail)
    address = f"{local}@{domain}{'c' * middle}{tail}"
    assert len(address) == length
    return address


@pytest.mark.anyio
async def test_the_http_rules_for_register_and_sign_in(migrated_db, clock):
    from tests.dbkit import owner_sql

    flush_redis()
    owner_sql(migrated_db, "DELETE FROM users WHERE lower(email) = 'nikhil@example.invalid'")  # the catalogue test's row
    async with api(settings_for(migrated_db, PASSWORD_MIN_LENGTH="12", RATE_LIMIT_REGISTER_IP_PER_HOUR="25"), clock) as c:
        short = await c.post("/api/auth/register", json={"email": "short@example.com", "password": "abcdefghijk"})
        long_ = await c.post("/api/auth/register", json={"email": "deva@example.com", "password": "क" * 25})
        latin = await c.post("/api/auth/register", json={"email": "latin@example.com", "password": "L" * 72})
        c.cookies.clear()
        twice = await c.post("/api/auth/register", json={"email": "LATIN@example.com", "password": "L" * 72})
        wrong = await c.post("/api/auth/login", json={"email": "latin@example.com", "password": "L" * 71 + "M"})
        unknown = await c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "L" * 72})
        nikhil = await c.post("/api/auth/register", json={"email": "Nikhil@Example.invalid", "password": "L" * 72})
        c.cookies.clear()
        e255 = await c.post("/api/auth/register", json={"email": _email(255), "password": "L" * 72})
        e254 = await c.post("/api/auth/register", json={"email": _email(254), "password": "L" * 72})
    err = lambda r: (r.status_code, r.json()["error"]["code"], r.json()["error"]["message"])  # noqa: E731
    assert err(short) == (422, "VALIDATION_FAILED",
                          "Your password must be at least 12 characters. It does not have to contain numbers or symbols.")
    assert err(long_) == (422, "VALIDATION_FAILED", "Your password is too long. The limit is 72 bytes and yours is 75. "
                          "Most characters count as one byte; accented and non-Latin characters count as two, three or four.")
    assert app_sql(migrated_db, "SELECT count(*) FROM users WHERE email = 'deva@example.com'") == [(0,)]  # never truncated
    assert latin.status_code == 201, latin.text
    assert twice.status_code == 409 and twice.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (401, "CREDENTIALS_INVALID")
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (401, "CREDENTIALS_INVALID")
    assert nikhil.status_code == 201
    assert app_sql(migrated_db, "SELECT email FROM users WHERE lower(email) = 'nikhil@example.invalid'") == [("Nikhil@Example.invalid",)]
    assert e255.status_code == 422 and e255.json()["error"]["code"] == "VALIDATION_FAILED"
    assert e254.status_code == 201, e254.text


def test_to_thread_run_sync_runs_bcrypt_for_the_auth_router():
    files = [BACKEND_DIR / "app" / "api" / "auth.py", *(BACKEND_DIR / "app" / "domain" / "accounts").rglob("*.py")]
    assert sum(p.read_text(encoding="utf-8").count("to_thread.run_sync") for p in files) >= 1


@pytest.mark.anyio
async def test_the_password_appears_in_no_stdout_line_and_no_response_body(migrated_db, clock, capsys):
    import io
    import logging

    from app.core.logging import configure_logging

    flush_redis()
    stream = io.StringIO()
    configure_logging(level="DEBUG", service="api", instance_id="test0001", now=clock.now, stream=stream)
    try:
        async with api(settings_for(migrated_db, LOG_LEVEL="DEBUG"), clock) as c:
            r = await c.post("/api/auth/register", json={"email": "horse99@example.com", "password": "Correct-Horse-99!"})
    finally:
        logging.getLogger().handlers.clear()
        logging.getLogger().setLevel(logging.WARNING)
    assert r.status_code == 201, r.text
    lines = (stream.getvalue() + capsys.readouterr().out).splitlines()
    assert any("/api/auth/register" in ln for ln in lines)  # the capture covered the request
    assert [ln for ln in lines if "Correct-Horse-99!" in ln] == []
    assert "Correct-Horse-99!" not in r.text

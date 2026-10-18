"""S-ACC-02 - the password rules, bcrypt off the event loop, one verification on every branch
(P-ACC-01 rows 4-6, P-ACC-03, EP-ACC-01, EP-ACC-02).

NOT covered here: the reset-confirm half of the 11-character clause. EP-ACC-06 ships in Phase 5
(SRC-004 JC-R6-02) and does not exist in this build; that clause is re-run against it there.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

from app.core import security
from app.domain import accounts
from tests.acc._support import api, flush_redis, settings_for
from tests.dbkit import app_sql, insert_user

pytestmark = pytest.mark.anyio

DEVANAGARI = "पासवर्ड" * 4  # P-ACC-01 worked example input B: 28 code points, 84 UTF-8 bytes


@pytest.fixture(autouse=True)
def _empty_buckets():
    flush_redis()


def _short_message(n: int) -> str:
    return f"Your password must be at least {n} characters. It does not have to contain numbers or symbols."


async def test_eleven_characters_is_refused_with_the_interpolated_floor(migrated_db, clock):
    async with api(settings_for(migrated_db, PASSWORD_MIN_LENGTH="12"), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "eleven@example.com", "password": "abcdefghijk"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"
    assert r.json()["error"]["message"] == _short_message(12)


async def test_the_floor_is_read_from_configuration_not_a_literal(migrated_db, clock):
    async with api(settings_for(migrated_db, PASSWORD_MIN_LENGTH="14"), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "fourteen@example.com", "password": "abcdefghijkl"})
    assert r.status_code == 422
    assert r.json()["error"]["message"] == _short_message(14)


async def test_84_bytes_is_refused_quoting_the_submitted_byte_count(migrated_db, clock):
    assert (len(DEVANAGARI), len(DEVANAGARI.encode("utf-8"))) == (28, 84)
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "bytes@example.com", "password": DEVANAGARI})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["byte_length"] == 84
    assert error["message"] == ("Your password is too long. The limit is 72 bytes and yours is 84. Most characters count "
                                "as one byte; accented and non-Latin characters count as two, three or four.")


async def test_spaces_are_kept_and_no_composition_rule_applies(migrated_db, clock):
    async with api(settings_for(migrated_db), clock) as c:
        a = await c.post("/api/auth/register", json={"email": "horse@example.com", "password": "correct horse battery"})
        b = await c.post("/api/auth/register", json={"email": "spaces@example.com", "password": " leading space kept "})
        lower = await c.post("/api/auth/register", json={"email": "lower@example.com", "password": "abcdefghijkl"})
        trimmed = await c.post("/api/auth/login", json={"email": "spaces@example.com", "password": "leading space kept"})
        exact = await c.post("/api/auth/login", json={"email": "spaces@example.com", "password": " leading space kept "})
    assert (a.status_code, b.status_code, lower.status_code) == (201, 201, 201)
    assert trimmed.status_code == 401 and trimmed.json()["error"]["code"] == "CREDENTIALS_INVALID"
    assert exact.status_code == 200


def test_72_is_a_literal_and_the_floor_is_not():
    source = (Path(accounts.__file__)).read_text(encoding="utf-8")
    assert "PASSWORD_MIN_LENGTH" in source or "min_length" in source
    assert not re.search(r"at least 12 characters", source)


async def test_bcrypt_hashing_runs_off_the_event_loop_thread(migrated_db, clock, monkeypatch):
    seen: list[bool] = []
    real = security.hash_password

    def recording(*args, **kwargs):
        seen.append(threading.current_thread() is threading.main_thread())
        return real(*args, **kwargs)

    monkeypatch.setattr(security, "hash_password", recording)
    assert threading.current_thread() is threading.main_thread()  # the async handler runs on this loop
    async with api(settings_for(migrated_db), clock) as c:
        r = await c.post("/api/auth/register", json={"email": "thread@example.com", "password": "correct horse battery"})
    assert r.status_code == 201
    assert seen == [False]


async def test_sign_in_verifies_exactly_once_on_every_branch(migrated_db, clock, monkeypatch):
    calls: list[int] = []
    real = security.verify_password

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(security, "verify_password", counting)
    insert_user(migrated_db, role="manager", email="nopassword@example.com",
                password_hash=accounts.unusable_password_hash(4))
    async with api(settings_for(migrated_db), clock) as c:
        await c.post("/api/auth/register", json={"email": "known@example.com", "password": "correct horse battery"})
        results = []
        for email, password in (("nobody@example.com", "correct horse battery"),
                                ("known@example.com", "wrong horse battery"),
                                ("nopassword@example.com", "correct horse battery")):
            before = len(calls)
            r = await c.post("/api/auth/login", json={"email": email, "password": password})
            results.append((len(calls) - before, r.status_code, r.json()["error"]["code"]))
    assert results == [(1, 401, "CREDENTIALS_INVALID")] * 3


async def test_password_hash_is_not_null_and_no_two_unused_accounts_share_a_hash(migrated_db):
    insert_user(migrated_db, role="manager", password_hash=accounts.unusable_password_hash(4))
    insert_user(migrated_db, role="manager", password_hash=accounts.unusable_password_hash(4))
    assert app_sql(migrated_db, "SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public' "
                                "AND table_name = 'users' AND column_name = 'password_hash'") == [("NO",)]
    assert app_sql(migrated_db, "SELECT count(*) - count(DISTINCT password_hash) FROM users "
                                "WHERE last_signed_in_at IS NULL") == [(0,)]


def test_no_assertion_in_this_module_reads_a_clock_or_sleeps():
    rx = re.compile(r"time\.time|time\.monotonic|time\.perf_counter|datetime\.now|datetime\.utcnow|sleep\(")
    assert [ln for ln in Path(__file__).read_text(encoding="utf-8").splitlines() if rx.search(ln)] == []

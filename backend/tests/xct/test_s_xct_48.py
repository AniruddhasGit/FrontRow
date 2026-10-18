"""S-XCT-48 (PRD P-XCT-32): every seeded account signs in with SEED_DEFAULT_PASSWORD, and no credential is
committed, printed or written.

NOT covered here (the row stays open on them, see the lane report): `rg -n 'SEED_DEFAULT_PASSWORD' backend/app`
returning 0 hits - backend/app/core/config.py still declares SeedSettings, which the foundation lane owns;
and the repository-wide `rg -nP '\\$2[aby]\\$\\d\\d\\$' .` returning 0 hits - two test fixtures outside this lane
(tests/dbkit.py, tests/acc/test_s_acc_10.py) carry a literal bcrypt prefix.
"""

from __future__ import annotations

import pytest

from app.core import security
from tests.acc._support import api, flush_redis, settings_for
from tests.dbkit import owner_sql
from tests.seed.kit import DOMAIN, PASSWORD, empty_db, one, run_seed, run_seed_process, seed, seeded, table_counts  # noqa: F401
from tests.xct._support import REPO, rg

ENV_EXAMPLE_VALUE = next(ln.split("=", 1)[1] for ln in (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
                         if ln.startswith("SEED_DEFAULT_PASSWORD="))


@pytest.mark.parametrize("value,needle", [
    (None, "SEED_DEFAULT_PASSWORD"),
    ("", "SEED_DEFAULT_PASSWORD"),
    ("a" * 11, "12 characters"),
    ("क" * 25, "72 bytes"),  # 25 Devanagari characters = 75 bytes: bcrypt would silently ignore 3
    (ENV_EXAMPLE_VALUE, "placeholder"),
])
def test_a_missing_short_long_or_placeholder_password_exits_before_any_write(empty_db, value, needle):
    before = table_counts(empty_db)
    result = run_seed_process(empty_db.app_url, password=value)
    assert result.returncode != 0
    assert needle in result.stdout + result.stderr
    assert "SEED_DEFAULT_PASSWORD" in result.stdout + result.stderr
    assert "WARNING" not in (result.stdout + result.stderr).upper()
    assert table_counts(empty_db) == before


def test_the_two_bounds_are_counted_in_their_own_units():
    assert len("क" * 25) == 25 >= 12 and len(("क" * 25).encode()) == 75
    assert len("क" * 24) == 24 and len(("क" * 24).encode()) == 72  # the ceiling itself is allowed


def test_the_placeholder_is_refused_by_value_not_by_pattern():
    assert seed.PASSWORD_PLACEHOLDER == ENV_EXAMPLE_VALUE


def test_one_hash_with_the_registration_function_reused_across_63_accounts():
    from tests.dbkit import create_database, drop_database

    assert seed.hash_password is security.hash_password  # the registration path's function, not a copy
    calls = []

    def counting(password, cost):
        calls.append(cost)
        return security.hash_password(password, cost)

    db = create_database(migrate=True)
    try:
        code, _ = run_seed(db.app_url, hasher=counting)
        assert code == 0
        assert calls == [4]  # BCRYPT_COST, set to 4 for speed by the kit
        assert one(db, "SELECT count(*) FROM users") == 63
        assert one(db, "SELECT count(DISTINCT password_hash) FROM users") == 1
        assert one(db, "SELECT password_hash FROM users LIMIT 1").startswith("$2b$" + "04$")
    finally:
        drop_database(db)


def test_the_addresses_are_deterministic_at_the_reserved_domain(seeded):
    db, _ = seeded
    emails = [e for (e,) in owner_sql(db, "SELECT email FROM users ORDER BY email")]
    expected = sorted([f"admin-01@{DOMAIN}"] + [f"manager-{m:02d}@{DOMAIN}" for m in range(1, 13)]
                      + [f"customer-{c:02d}@{DOMAIN}" for c in range(1, 51)])
    assert emails == expected
    assert DOMAIN == "demo.frontrow.invalid"
    assert dict(owner_sql(db, "SELECT role, count(*) FROM users GROUP BY 1")) == {"admin": 1, "manager": 12, "customer": 50}


def test_stdout_lists_counts_and_addresses_and_never_the_password(seeded):
    _, lines = seeded
    for role, n in (("admin", 1), ("manager", 12), ("customer", 50)):
        i = lines.index(f"{role}: {n}")
        assert [ln.strip() for ln in lines[i + 1:i + 1 + n]] == [e for e, r in seed.accounts(DOMAIN) if r == role]
    assert not [ln for ln in lines if PASSWORD in ln]


def test_the_seed_writes_no_file(seeded):
    assert rg(r"\bopen\(|write_text|write_bytes", "scripts/seed.py") == []


def test_managers_map_to_screens_two_per_screen(seeded):
    db, _ = seeded
    got = dict(owner_sql(db, "SELECT split_part(u.email, '@', 1), s.name FROM manager_screen_assignment a "
                             "JOIN users u ON u.id = a.user_id JOIN screen s ON s.id = a.screen_id"))
    assert got == {f"manager-{m:02d}": f"SCREEN {(m - 1) // 2 + 1}" for m in range(1, 13)}


@pytest.mark.anyio
async def test_the_admin_and_all_fifty_customers_sign_in_with_the_value_that_was_set(seeded, clock):
    db, _ = seeded
    flush_redis()
    settings = settings_for(db, RATE_LIMIT_LOGIN_IP_PER_15MIN="1000")
    async with api(settings, clock) as client:
        r = await client.post("/api/auth/login", json={"email": f"admin-01@{DOMAIN}", "password": PASSWORD})
        assert r.status_code == 200, r.text
        assert security.SESSION_COOKIE in r.cookies
        ok = 0
        for c in range(1, 51):
            client.cookies.clear()
            r = await client.post("/api/auth/login", json={"email": f"customer-{c:02d}@{DOMAIN}", "password": PASSWORD})
            assert r.status_code == 200, (c, r.text)
            ok += 1
        assert ok == 50

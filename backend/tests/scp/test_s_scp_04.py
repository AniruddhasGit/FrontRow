"""S-SCP-04 (PRD P-SCP-02/03/10/16, FR-ADR-040/048): the migrated schema carries no table or column for an
excluded capability - no refund, loyalty, tier, discount, fee, tax, concession or check-in - while
password_reset_token.used_at, which belongs to an included feature, still exists.

Run against a database built by `alembic upgrade head` (the real migrate command) from empty.
"""

from __future__ import annotations

import re

from tests.dbkit import owner_sql

BOOKING_COLUMNS = re.compile(r"used_at|discount|fee|tax|refund|\bpoints\b|concession")
TABLES = re.compile(r"refund|loyalty|point|tier|membership|discount|coupon|voucher|convenience_fee|tax|concession|"
                    r"order_line|checkin|check_in")
USERS_COLUMNS = re.compile(r"tier|\bpoints\b|loyalty|membership")


def _columns(db, table: str) -> list[str]:
    return [c for (c,) in owner_sql(db, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                                        "AND table_name = %s", (table,))]


def test_booking_has_no_excluded_column(migrated_db):
    columns = _columns(migrated_db, "booking")
    assert "reference" in columns  # the table exists, so an empty match is not vacuous
    assert [c for c in columns if BOOKING_COLUMNS.search(c)] == []


def test_no_table_names_an_excluded_capability(migrated_db):
    tables = [t for (t,) in owner_sql(migrated_db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert len(tables) >= 22
    assert [t for t in tables if TABLES.search(t)] == []


def test_users_has_no_tier_points_loyalty_or_membership_column(migrated_db):
    columns = _columns(migrated_db, "users")
    assert "email" in columns
    assert [c for c in columns if USERS_COLUMNS.search(c)] == []


def test_password_reset_token_used_at_is_exempt_and_still_exists(migrated_db):
    assert "used_at" in _columns(migrated_db, "password_reset_token")
    # the exemption is the column on THAT table only; the same name on booking would fail above
    assert BOOKING_COLUMNS.search("used_at")


def test_the_patterns_catch_what_they_are_for():
    """Watched failing: each pattern matches a name it exists to refuse, so a passing scan is not a broken regex."""
    assert all(BOOKING_COLUMNS.search(n) for n in ("refunded_at", "discount_paise", "convenience_fee_paise", "tax_paise", "points"))
    assert not BOOKING_COLUMNS.search("checkpoints")
    assert all(TABLES.search(n) for n in ("refund", "loyalty_account", "membership_tier", "coupon", "order_line", "check_in"))
    assert all(USERS_COLUMNS.search(n) for n in ("tier", "points", "loyalty_id", "membership_level"))

"""S-XCT-04 - the seat-occupancy unique constraint is created in the Phase 2 migration, in the same
revision as the table - plus the proof that the migration creates exactly docs/06 DataModel/schema.sql.

Database half of the seat guarantee (P-XCT-01). The Redis half is Phase 4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.dbkit import BACKEND_DIR, create_database, datamodel_dir, drop_database, owner_sql, run_psql, run_sql

VERSIONS = BACKEND_DIR / "migrations" / "versions"
MIGRATIONS = BACKEND_DIR / "migrations"


def _files_matching(root: Path, pattern: str, flags: int = 0) -> list[Path]:
    """The equivalent of `rg -l PATTERN root` (rg is not in the test image)."""
    rx = re.compile(pattern, flags)
    return sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and rx.search(p.read_text(encoding="utf-8")))


# ---- the criterion, clause by clause ----------------------------------------------------------------


def test_upgrade_head_on_empty_database_creates_exactly_one_unique_constraint_on_booking_seat(migrated_db):
    rows = owner_sql(migrated_db, "SELECT conname FROM pg_constraint WHERE conrelid = 'booking_seat'::regclass AND contype = 'u'")
    assert rows == [("uq_booking_seat__showtime_id_seat_id",)]


def test_table_and_its_unique_constraint_are_written_in_the_same_single_revision_file():
    creates = _files_matching(VERSIONS, re.escape("create_table('booking_seat'"))
    pairs = _files_matching(VERSIONS, re.escape("'showtime_id', 'seat_id'"))
    assert len(creates) == 1
    assert creates == pairs


def test_no_revision_drops_a_constraint():
    assert _files_matching(MIGRATIONS, r"drop_constraint|DROP CONSTRAINT", re.IGNORECASE) == []


def test_the_guard_is_total_no_where_clause_and_not_a_partial_index(migrated_db):
    (definition,) = owner_sql(
        migrated_db,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'booking_seat'::regclass AND contype = 'u'",
    )[0]
    assert definition == "UNIQUE (showtime_id, seat_id)"
    indexdefs = [r[0] for r in owner_sql(migrated_db, "SELECT indexdef FROM pg_indexes WHERE tablename = 'booking_seat'")]
    assert indexdefs, "booking_seat has no indexes at all"
    assert all("WHERE" not in d.upper() for d in indexdefs), indexdefs


def test_the_constraint_refuses_a_second_seller(migrated_db):
    """Not in the criterion's text, but it is what the constraint is for: watch it refuse."""
    import psycopg

    from tests.dbkit import insert_booking, insert_showtime, insert_user

    st = insert_showtime(migrated_db)
    insert_booking(migrated_db, user_id=insert_user(migrated_db, role="customer"), showtime=st, price_paise=25000, reference="AAAAAAA2")
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_booking(migrated_db, user_id=insert_user(migrated_db, role="customer"), showtime=st, price_paise=25000, reference="AAAAAAA3")


# ---- the migration is schema.sql, nothing more and nothing less --------------------------------------

_CATALOG = {
    "columns": """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attidentity,
               coalesce(pg_get_expr(d.adbin, d.adrelid), '')
          FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
          LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
         WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
           AND c.relname <> 'alembic_version'""",
    "constraints": """
        SELECT conrelid::regclass::text, conname, contype, pg_get_constraintdef(oid)
          FROM pg_constraint WHERE connamespace = 'public'::regnamespace AND conrelid::regclass::text <> 'alembic_version'""",
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename <> 'alembic_version'",
    "grants": """
        SELECT table_name, privilege_type FROM information_schema.role_table_grants
         WHERE grantee = 'frontrow_app' AND table_schema = 'public'""",
    "owners": "SELECT relname, relkind, pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relname NOT LIKE 'alembic_version%'",
    "sequence_grants": """
        SELECT c.relname, has_sequence_privilege('frontrow_app', c.oid, 'USAGE'), has_sequence_privilege('frontrow_app', c.oid, 'SELECT')
          FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'""",
}


def _catalog(admin_url: str) -> dict[str, list]:
    return {k: sorted(run_sql(admin_url, q)) for k, q in _CATALOG.items()}


@pytest.fixture(scope="module")
def schema_sql_db():
    """A second throwaway database built from docs/06 DataModel/schema.sql itself, as the owner."""
    db = create_database(migrate=False)
    run_psql(db.owner_url, "-f", str(datamodel_dir() / "schema.sql"), check=True)
    yield db
    drop_database(db)


def test_migrated_catalog_is_identical_to_the_catalog_schema_sql_produces(migrated_db, schema_sql_db):
    migrated, reference = _catalog(migrated_db.admin_url), _catalog(schema_sql_db.admin_url)
    for part in _CATALOG:
        assert migrated[part] == reference[part], part
    # Not vacuous: the reference really is the 22-table model.
    assert len({r[0] for r in reference["columns"]}) == 22


def test_verify_invariants_sql_passes_as_the_application_role(migrated_db):
    """docs/06 DataModel/checks/verify_invariants.sql, verbatim, connected as frontrow_app."""
    result = run_psql(migrated_db.app_url, "-f", str(datamodel_dir() / "checks" / "verify_invariants.sql"))
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "FAIL" not in out
    assert len(re.findall(r"NOTICE:\s+PASS ", out)) >= 30, out


def test_the_orm_mirror_matches_the_migrated_columns(migrated_db):
    """app/models mirrors the schema and never defines it (AGENT_CONTRACT rule 8). Drift fails here."""
    from sqlalchemy.dialects import postgresql

    from app.models import metadata

    pg = {(t, c): (typ, notnull) for t, c, typ, notnull, *_ in _catalog(migrated_db.admin_url)["columns"]}
    mirror = {
        (table.name, col.name): (col.type.compile(dialect=postgresql.dialect()).lower(), not col.nullable)
        for table in metadata.sorted_tables
        for col in table.columns
    }
    assert mirror == pg

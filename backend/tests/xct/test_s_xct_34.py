"""S-XCT-34 (P-XCT-20, FR-ADR-070): the backup specification, and a restore rehearsal with a recorded outcome.

The local rehearsal: a migrated throwaway database with the known booking written into it, `pg_dump -Fc`, `pg_restore`
into a SECOND new database, then scripts/restore_rehearsal.py with DATABASE_URL alone pointed at the new one. The RDS
half - a restore to a new RDS instance - is Zone C and has not run (the row's AWS clause stays Blocked).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

import pytest

from tests.dbkit import create_database, drop_database, owner_sql
from tests.pay import kit
from tests.xct._support import DEPLOY, REPO, prep_queue, spec_files

SCRIPT = str(REPO / "scripts" / "restore_rehearsal.py")


def test_the_prep_queue_row_and_its_spec_carry_every_required_sentence():
    [row] = [r for r in prep_queue() if "RDS automated backups" in r["Item"]]
    assert row["Needed by"] == "Phase 2"
    [spec] = spec_files(row["Spec"])
    text = (DEPLOY / spec).read_text(encoding="utf-8")
    for phrase in ("retention 7 days", "point-in-time recovery", "a backup window outside the cinema's busy period",
                   "a manual snapshot before every migration", "a restore creates a new RDS instance with a new endpoint",
                   "deleting an instance without a final snapshot deletes its automated backups with it",
                   "a corruption discovered in week three is not recoverable from an automated backup",
                   "forever retention and a 7-day backup window are different guarantees",
                   "Redis is not backed up: it holds locks and cache",
                   "S3 posters are not backed up: nothing deletes a poster and a new poster is a new key"):
        assert phrase in text, phrase


def _rehearse(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("RESTORE_OPERATOR", "DATABASE_URL")}
    env.update(env_overrides)
    return subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True, text=True, timeout=60)


def test_the_rehearsal_refuses_to_run_without_an_operator():
    proc = _rehearse({"DATABASE_URL": "postgresql://x:y@db.invalid:5432/frontrow"})
    assert proc.returncode != 0
    assert "RESTORE_OPERATOR" in proc.stderr


def test_a_dump_restored_to_a_new_database_reads_the_known_booking_back(migrated_db):
    w = kit.world7(migrated_db, base=24999)
    kit.add_seats(migrated_db, w["screen"], w["premium"], [(512, "C", 12), (513, "C", 13)], [kit.SHOWTIME])
    u = kit.user(migrated_db)
    with_booking = owner_sql(migrated_db, "INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, "
                                          "captured_at) VALUES ('captured', 56248, 'restore-rehearsal', now(), now(), now()) RETURNING id")
    pay = with_booking[0][0]
    b = owner_sql(migrated_db, "INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status, created_at) "
                               "VALUES ('K7M2QX9C', %s, %s, %s, 56248, 'confirmed', now()) RETURNING id", (u, kit.SHOWTIME, pay))[0][0]
    for seat in (512, 513):
        owner_sql(migrated_db, "INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, "
                               "uplift_basis_points_applied, seat_category_id) SELECT %s, %s, id, 28124, 24999, 1250, seat_category_id "
                               "FROM seat WHERE id = %s", (b, kit.SHOWTIME, seat))
    restored = create_database(migrate=False)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dump = os.path.join(tmp, "frontrow.dump")
            subprocess.run(["pg_dump", "-Fc", "-f", dump, "-d", migrated_db.admin_url], check=True, capture_output=True, timeout=120)
            # The test image's client tools are newer than the PostgreSQL 16 server, and pg_restore writes
            # `SET transaction_timeout`, a setting 16 does not have. So the archive is rendered to SQL, that one line
            # dropped, and the rest applied with ON_ERROR_STOP - every other statement must succeed.
            sql = subprocess.run(["pg_restore", "-f", "-", dump], check=True, capture_output=True, text=True, timeout=120).stdout
            sql = "\n".join(ln for ln in sql.splitlines() if not ln.startswith("SET transaction_timeout"))
            r = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", restored.admin_url], input=sql,
                               capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr
        # The application's own connection string, with ONLY the database changed to the restored one.
        proc = _rehearse({"RESTORE_OPERATOR": "lane-p7-ops", "DATABASE_URL": restored.app_url})
    finally:
        drop_database(restored)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    [line] = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    assert set(line) == {"operator", "run_at", "restored_instance", "outcome", "reference", "seats", "total_paise"}
    assert (line["operator"], line["outcome"]) == ("lane-p7-ops", "pass")
    assert restored.name in line["restored_instance"] and "local-dev" not in line["restored_instance"]
    datetime.fromisoformat(line["run_at"])  # a dated claim: it parses as an instant
    assert line["reference"] == "FR-K7M2-QX9C"
    assert line["seats"] == [["C12", "Premium", 28124], ["C13", "Premium", 28124]]
    assert line["total_paise"] == 56248 == 2 * 28124


@pytest.fixture(scope="module")
def migrated_db():
    # Its own database: the rehearsal dumps the whole thing, so it must hold nothing another module wrote.
    db = create_database(migrate=True)
    yield db
    drop_database(db)

"""S-XCT-33 - migrations run as a separate explicit step and never on boot.

Covered: no migration code path in backend/app; alembic only inside the entrypoint's migrate branch;
migrate exits with the migration's status; the API against an UNMIGRATED database starts, is live and
ready, and answers 500 at the first query that needs a table; every downgrade is one raise; the LOCK
marker; no destructive operations; the application role is not a superuser; the docs/30 Deployment runbook
strings; the entrypoint accepts exactly four commands, api, worker, migrate and seed (the worker arrived in Phase 5).
"""

from __future__ import annotations

import ast
import re

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import db
from app.main import create_app
from app.models import movie
from tests.dbkit import BACKEND_DIR, app_settings, app_sql, create_database, drop_database, owner_sql, run_migrate
from tests.xct._support import REPO

VERSIONS = BACKEND_DIR / "migrations" / "versions"
REVISIONS = sorted(p for p in VERSIONS.glob("*.py"))


def _lines(root, pattern, flags=0):
    rx = re.compile(pattern, flags)
    return [
        (p, i, line)
        for p in ([root] if root.is_file() else [q for q in root.rglob("*") if q.is_file() and "__pycache__" not in q.parts])
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if rx.search(line)
    ]


def test_no_application_code_can_apply_a_migration():
    assert _lines(BACKEND_DIR / "app", r"alembic", re.IGNORECASE) == []
    assert _lines(BACKEND_DIR / "app", r"upgrade\(") == []


def test_alembic_appears_in_the_entrypoint_only_inside_the_migrate_branch():
    text = (BACKEND_DIR / "entrypoint.sh").read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(text) if ln.strip() == "migrate)")
    end = next(i for i in range(start, len(text)) if text[i].strip() == ";;")
    hits = [i for i, ln in enumerate(text) if "alembic" in ln.lower()]
    assert hits and all(start < i < end for i in hits), hits
    assert any("exec alembic -c migrations/alembic.ini upgrade head" in text[i] for i in hits)


def test_the_entrypoint_accepts_exactly_four_commands_and_a_fifth_is_refused_naming_them():
    import subprocess

    text = (BACKEND_DIR / "entrypoint.sh").read_text(encoding="utf-8").splitlines()
    branches = {m.group(1) for ln in text if (m := re.fullmatch(r"\s*([a-z]+)\)", ln))}
    assert branches == {"api", "worker", "migrate", "seed"}
    r = subprocess.run(["sh", str(BACKEND_DIR / "entrypoint.sh"), "scheduler"], capture_output=True, text=True, timeout=30)
    assert r.returncode != 0
    assert "api | worker | migrate | seed" in r.stdout
    # api and worker exec a long-running process and nothing else: no alembic, no second command.
    for name in ("api", "worker"):
        start = next(i for i, ln in enumerate(text) if ln.strip() == f"{name})")
        end = next(i for i in range(start, len(text)) if text[i].strip() == ";;")
        body = [ln.strip() for ln in text[start + 1:end] if ln.strip() and not ln.strip().startswith("#")]
        assert body == [f"exec python -m app {name}"], body


def test_migrate_exits_zero_on_success_and_non_zero_with_the_migrations_status_on_failure():
    good = create_database(migrate=False)
    try:
        ok = run_migrate(good.owner_url)
        assert ok.returncode == 0, ok.stderr
        # Re-running is a no-op that still exits 0: head is already applied.
        assert run_migrate(good.owner_url).returncode == 0
        # As the APPLICATION role it cannot create tables: the migration fails and so does the command.
        fresh = create_database(migrate=False)
        try:
            bad = run_migrate(fresh.app_url)
            assert bad.returncode != 0
            assert "permission denied" in bad.stderr.lower()
            assert app_sql(fresh, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'") == [(0,)]  # all or nothing
        finally:
            drop_database(fresh)
    finally:
        drop_database(good)


def test_the_api_against_an_unmigrated_database_starts_and_fails_at_the_first_query(clock):
    import os

    from app.core.readiness import postgres_probe, redis_probe
    from redis.asyncio import Redis

    behind = create_database(migrate=False)  # no revision applied: the table itself is missing
    try:
        settings = app_settings(behind, REDIS_URL=os.environ["TEST_REDIS_URL"])
        redis_client = Redis.from_url(settings.REDIS_URL)
        probes = [postgres_probe(settings.DATABASE_URL, settings.DB_CONNECT_TIMEOUT_MS), redis_probe(redis_client, 1000)]
        application = create_app(settings, clock=clock, probes=probes)

        @application.get("/__test__/first-query")
        async def first_query(conn=Depends(db)):
            return {"n": len((await conn.execute(select(movie.c.id))).all())}

        with TestClient(application, raise_server_exceptions=False) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200, client.get("/health/ready").text
            r = client.get("/__test__/first-query")
            assert r.status_code == 500
            assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    finally:
        drop_database(behind)


def test_the_api_one_revision_behind_starts_healthy_and_fails_at_the_first_request_touching_a_new_column(clock):
    """The AC's case as written: the database at 0001, the code at head, a request reading a column 0002 adds.
    ponytail: pinned to the 0001 -> 0002 pair (showtime.created_at); a later revision keeps this a valid
    one-behind case for 0002 and gets its own pair only if its own column needs proving."""
    import os
    import subprocess

    from app.core.readiness import postgres_probe, redis_probe
    from app.models import showtime
    from redis.asyncio import Redis

    behind = create_database(migrate=False)
    try:
        r = subprocess.run(["alembic", "-c", "migrations/alembic.ini", "upgrade", "0001"], cwd=BACKEND_DIR,
                           env={**os.environ, "DATABASE_URL": behind.owner_url}, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        assert owner_sql(behind, "SELECT version_num FROM alembic_version") == [("0001",)]
        settings = app_settings(behind, REDIS_URL=os.environ["TEST_REDIS_URL"])
        redis_client = Redis.from_url(settings.REDIS_URL)
        probes = [postgres_probe(settings.DATABASE_URL, settings.DB_CONNECT_TIMEOUT_MS), redis_probe(redis_client, 1000)]
        application = create_app(settings, clock=clock, probes=probes)

        @application.get("/__test__/new-column")
        async def new_column(conn=Depends(db)):
            return {"n": len((await conn.execute(select(showtime.c.created_at))).all())}

        @application.get("/__test__/old-column")
        async def old_column(conn=Depends(db)):
            return {"n": len((await conn.execute(select(showtime.c.id))).all())}

        with TestClient(application, raise_server_exceptions=False) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 200, client.get("/health/ready").text
            assert client.get("/__test__/old-column").json() == {"n": 0}  # the table is there; only the column is new
            r = client.get("/__test__/new-column")
            assert r.status_code == 500
            assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    finally:
        drop_database(behind)


@pytest.mark.parametrize("revision", REVISIONS, ids=lambda p: p.name)
def test_every_downgrade_is_a_single_raise(revision):
    tree = ast.parse(revision.read_text(encoding="utf-8"))
    (downgrade,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "downgrade"]
    assert len(downgrade.body) == 1 and isinstance(downgrade.body[0], ast.Raise)
    assert ast.unparse(downgrade.body[0].exc).startswith("NotImplementedError")


def test_there_is_at_least_one_revision():
    assert REVISIONS


def test_every_revision_touching_audit_log_or_booking_seat_carries_a_lock_comment():
    touching = {p for p, *_ in _lines(VERSIONS, r"audit_log|booking_seat")}
    locked = {p for p, *_ in _lines(VERSIONS, r"# LOCK:")}
    assert touching and touching <= locked


def test_no_revision_drops_or_alters_a_column_or_table():
    assert _lines(VERSIONS, r"drop_column|drop_table|alter_column") == []


def test_the_application_role_is_not_a_superuser(migrated_db):
    assert app_sql(migrated_db, "SELECT rolsuper FROM pg_roles WHERE rolname = current_user") == [(False,)]
    assert app_sql(migrated_db, "SELECT current_user") == [("frontrow_app",)]


def test_the_runbook_names_the_symptom_and_the_one_directional_deploy_order():
    from tests.xct._support import rg

    assert rg("starts healthy and fails at the first query touching a new column", "docs/30 Deployment", fixed=True)
    hits = rg("1 manual snapshot, 2 one-off migrate task, 3 verify the task exited 0, 4 update the service",
              "docs/30 Deployment", fixed=True)
    assert hits
    (path,) = {h[0] for h in hits}
    text = (REPO / path).read_text(encoding="utf-8")
    assert "reversing 2 and 4 runs new code against an old schema" in text
    assert "skipping 1 makes 2 unrecoverable after seven days" in text

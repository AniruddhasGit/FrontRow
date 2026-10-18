"""S-XCT-49 (PRD P-XCT-32): the deployed seed run is specified as a one-off task on its own task definition
family, and the build session creates none of it.

NOT covered here (the row stays open on it): the entrypoint's `worker` command, which arrives with the worker
in Phase 5 - so "alongside api, worker and migrate" and "0 'seed' hits in the worker branch" can only be
asserted for the branches that exist.
"""

from __future__ import annotations

import os
import re
import subprocess

from tests.dbkit import BACKEND_DIR, create_database, drop_database, owner_sql
from tests.xct._support import DEPLOY, REPO, prep_queue, rg, spec_files, strip_md

SPEC = DEPLOY / "P2_SEED_TASK.md"
ENTRYPOINT = BACKEND_DIR / "entrypoint.sh"


def _branches() -> dict[str, list[str]]:
    """The entrypoint's case branches by command name: the lines from `name)` to its `;;`."""
    lines = ENTRYPOINT.read_text(encoding="utf-8").splitlines()
    out: dict[str, list[str]] = {}
    for i, line in enumerate(lines):
        m = re.fullmatch(r"\s*([a-z*]+)\)", line)
        if m:
            end = next(j for j in range(i, len(lines)) if lines[j].strip() == ";;")
            out[m.group(1)] = lines[i + 1:end]
    return out


def _entrypoint(*argv: str, **env: str) -> subprocess.CompletedProcess:
    """The real entrypoint, run from the repository root - where scripts/seed.py sits at the same relative
    path as in the image (/srv/scripts/seed.py) - with every SEED_ variable cleared first."""
    base = {k: v for k, v in os.environ.items() if not k.startswith("SEED_") and k != "DATABASE_URL"}
    return subprocess.run(["sh", str(ENTRYPOINT), *argv], cwd=REPO, env={**base, "BCRYPT_COST": "4", **env},
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)


def test_the_entrypoint_has_a_seed_branch_and_the_api_branch_never_mentions_seed():
    branches = _branches()
    assert {"api", "migrate", "seed"} <= set(branches), branches.keys()
    assert any("scripts/seed.py" in line for line in branches["seed"])
    for name in ("api", "worker"):
        assert [ln for ln in branches.get(name, []) if "seed" in ln.lower()] == [], name


def test_seed_exits_with_the_seeds_own_status_on_a_refusal():
    # No SEED_DEFAULT_PASSWORD: the seed refuses with 78 (EX_CONFIG) before any write; the entrypoint must
    # hand that status back unchanged, not 0 and not its own 64.
    r = _entrypoint("seed", DATABASE_URL="postgresql://nobody@127.0.0.1:1/none")
    assert r.returncode == 78, (r.returncode, r.stdout, r.stderr)
    assert "SEED_DEFAULT_PASSWORD" in r.stderr


def test_seed_exits_zero_after_seeding_a_database():
    db = create_database(migrate=True)
    try:
        r = _entrypoint("seed", DATABASE_URL=db.app_url, SEED_DEFAULT_PASSWORD="seed-test-password-only")
        assert r.returncode == 0, (r.stdout[-2000:], r.stderr[-2000:])
        assert owner_sql(db, "SELECT count(*) FROM cinema") == [(1,)]
        assert "admin: 1" in r.stdout
    finally:
        drop_database(db)


def test_the_image_carries_scripts_so_the_seed_command_can_run_there():
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile[dockerfile.index("AS runtime"):]
    assert re.search(r"^COPY scripts/seed\.py \./scripts/seed\.py$", runtime, re.M)
    assert re.search(r"^COPY scripts/assets \./scripts/assets$", runtime, re.M)
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    # The build context is the repository root, because scripts/ sits beside backend/ (SRC-002 §11).
    assert "context: ./backend" not in compose
    assert compose.count("dockerfile: backend/Dockerfile") >= 3


def test_the_spec_is_found_through_the_queue_rows_spec_cell():
    (row,) = [r for r in prep_queue() if "one-off seed task" in strip_md(r["Item"])]
    assert [DEPLOY / f for f in spec_files(row["Spec"])] == [SPEC]


def test_the_seed_task_specification_carries_every_required_statement():
    text = SPEC.read_text(encoding="utf-8")
    for literal in ("a one-off ECS task", "a task definition family that is the seed's alone", "the same image",
                    "run once and deliberately by the client", "/frontrow/<environment>/SEED_DEFAULT_PASSWORD",
                    "SecureString", "valueFrom", "the execution role, not the task role",
                    "Acceptance criterion: sign in as admin-01@ with the value that was stored."):
        assert literal in text, literal
    assert "The service's task definition never carries the parameter." in text.replace("**", "")


def test_the_queue_carries_a_one_off_seed_task_row_needed_by_phase_2():
    rows = [r for r in prep_queue() if "one-off seed task" in strip_md(r["Item"])]
    assert len(rows) == 1
    assert strip_md(rows[0]["Needed by"]) == "Phase 2"


def test_the_build_session_creates_none_of_it():
    assert rg(r"register-task-definition|aws ssm put-parameter|aws iam (create|attach|put)|aws ecs run-task",
              "backend/app", "backend/migrations", "frontend/src", "scripts", "docker-compose.yml") == []

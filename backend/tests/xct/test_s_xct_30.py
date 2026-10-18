"""S-XCT-30 (PRD P-XCT-16): secrets reach the process as environment variables injected by the task
definition from SSM; the application never calls SSM."""

from __future__ import annotations

import re

from app.core.config import Settings

from ._support import DEPLOY, REPO, md_table_after, prep_queue, rg, spec_files, strip_md

EXEC_TREES = ("backend/app", "backend/migrations", "frontend/src", "scripts", "docker-compose.yml")


def test_the_application_never_calls_ssm_and_builds_only_s3_sqs_ses_clients():
    assert rg(r"ssm|get_parameter|parameter_store", "backend/app", ignore_case=True) == []
    clients = {m.group(1) for _, _, line in rg(r"boto3\.client\(['\"][a-z0-9]+", "backend/app") for m in [re.search(r"boto3\.client\(['\"]([a-z0-9]+)", line)]}
    assert clients <= {"s3", "sqs", "ses"}


def _ssm_spec() -> str:
    rows = [r for r in prep_queue() if "SSM Parameter Store" in strip_md(r["Item"])]
    assert len(rows) == 1
    assert rows[0]["Needed by"] == "Phase 1"
    files = spec_files(rows[0]["Spec"])
    assert len(files) == 1, files
    return (DEPLOY / files[0]).read_text(encoding="utf-8")


def test_the_ssm_spec_carries_every_required_literal():
    text = _ssm_spec()
    for literal in (
        "/frontrow/<environment>/<VARIABLE_NAME>",
        "SecureString",
        "AWS-managed key for SSM",
        "valueFrom",
        "the execution role, not the task role",
        "takes effect only on a new task deployment",
        "rotating JWT_SECRET invalidates every live session",
    ):
        assert literal in text, literal


def test_secure_and_plain_tables_are_disjoint_and_the_hold_ttl_is_plain():
    text = _ssm_spec()
    secure = {strip_md(r["Variable"]) for r in md_table_after(text, "## SecureString parameters")}
    plain = {strip_md(r["Variable"]) for r in md_table_after(text, "## Plain environment variables")}
    assert secure and plain
    assert secure & plain == set()
    assert "SEAT_HOLD_TTL_SECONDS" in plain and "SEAT_HOLD_TTL_SECONDS" not in secure
    assert not [ln for ln in text.splitlines() if "valueFrom" in ln and "SEAT_HOLD_TTL_SECONDS" in ln]
    # the two tables together are the api's whole inventory, so the task definition misses nothing
    assert secure | plain == set(Settings.model_fields)


def test_secrets_manager_appears_only_where_it_is_forbidden():
    hits = rg("secrets manager", "docs/30 Deployment", ignore_case=True, fixed=True)
    assert [h for h in hits if "forbidden" not in h[2].lower()] == []


def test_dotenv_is_git_ignored():
    # `git check-ignore .env` exits 0 on the host (recorded in the lane report); the image has no git,
    # so this asserts the ignore rule itself.
    assert ".env" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_no_credential_anywhere_in_the_repository_and_the_pattern_does_not_match_itself():
    pattern = r"(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-)"
    assert rg(pattern, ".") == []
    assert rg(pattern, "docs/05 Bible") == []


def test_the_build_session_creates_no_parameter_role_or_task_definition():
    assert rg(r"aws ssm (put-parameter|delete-parameter)|aws iam (create|attach|put)|register-task-definition", *EXEC_TREES) == []

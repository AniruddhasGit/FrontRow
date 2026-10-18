"""S-XCT-49 (PRD P-XCT-32): the deployed seed run is specified as a one-off task on its own task definition
family, and the build session creates none of it.

NOT covered here (the row stays open on them, see the lane report): the entrypoint's `seed` command (the
entrypoint and the Dockerfile that would copy scripts/ into the image belong to the foundation lane), and
resolving the specification THROUGH the Spec cell of AWS_PREP_QUEUE.md row 19, which is outside this lane.
"""

from __future__ import annotations

from tests.xct._support import DEPLOY, prep_queue, rg, strip_md

SPEC = DEPLOY / "P2_SEED_TASK.md"


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

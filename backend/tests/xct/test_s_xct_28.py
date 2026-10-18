"""S-XCT-28 (PRD P-XCT-14, S7.14): one alarm, specified and not built; missing data is breaching;
the unwatched list is published."""

from __future__ import annotations

from ._support import DEPLOY, prep_queue, rg, spec_files, strip_md

EXEC_TREES = ("backend/app", "backend/migrations", "frontend/src", "scripts", "docker-compose.yml")


def _alarm_row():
    rows = [r for r in prep_queue() if "CloudWatch alarm" in strip_md(r["Item"])]
    assert len(rows) == 1, [r["#"] for r in rows]
    return rows[0]


def test_exactly_one_alarm_row_needed_by_phase_1_naming_metric_topic_and_subscription():
    row = _alarm_row()
    item = strip_md(row["Item"])
    assert row["Needed by"] == "Phase 1"
    for literal in ("running-task-count < 1", "SNS topic", "email subscription"):
        assert literal in item, literal


def test_no_alarm_definition_of_any_kind_in_the_executable_trees():
    assert rg(r"put-metric-alarm|aws_cloudwatch_metric_alarm|AWS::CloudWatch::Alarm|AlarmName", *EXEC_TREES, ignore_case=True) == []


def _spec_text() -> str:
    files = spec_files(_alarm_row()["Spec"])
    assert len(files) == 1, files
    return (DEPLOY / files[0]).read_text(encoding="utf-8")


def test_the_spec_names_the_treatment_the_failure_and_the_acceptance():
    text = _spec_text()
    for literal in ("TreatMissingData: breaching", "INSUFFICIENT_DATA", "Acceptance criterion: stop the service, receive an email.", "Recommended, not adopted: an alarm on dead-letter queue depth."):
        assert literal in text, literal


def test_the_spec_publishes_the_unwatched_list():
    lines = _spec_text().splitlines()
    i = lines.index("## Not watched, and deliberately so")
    items = []
    for line in lines[i + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("- "):
            items.append(line)
    assert items and items[0].startswith("- dead-letter queue depth")
    assert any("S3 poster bucket" in it for it in items[1:])


def test_no_destination_address_is_committed():
    pattern = r"[\w.+-]+@(?!example\.invalid|demo\.frontrow\.invalid)[\w.-]+\.[a-z]{2,}"
    assert rg(pattern, *EXEC_TREES, ".env.example", "docs/30 Deployment", ignore_case=True) == []


def test_the_build_session_creates_no_alarm_topic_or_subscription():
    assert rg(r"put-metric-alarm|create-topic|sns subscribe", *EXEC_TREES) == []

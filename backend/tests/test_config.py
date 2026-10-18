"""P-XCT-15 / SRC-002 §7.1: every setting from the environment, and a crash at boot naming the
variable when one is missing or wrong."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import ConfigError, load_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_valid_environment_loads_with_ruled_defaults(valid_env):
    s = load_settings()
    assert s.DATABASE_URL.startswith("postgresql://")
    assert s.REDIS_URL.startswith("redis://")
    # Defaults are the values PRD S7.9 publishes, not values invented here.
    assert s.LOG_LEVEL == "INFO"
    assert s.API_PORT == 8000
    assert s.REDIS_CONNECT_TIMEOUT_MS == 500
    assert s.REDIS_COMMAND_TIMEOUT_MS == 500
    assert s.SHUTDOWN_DRAIN_TIMEOUT_SECONDS == 20
    assert s.READINESS_CACHE_TTL_SECONDS == 3
    # [JUDGMENT CALL] ASSUMED, no frozen source names it.
    assert s.DB_CONNECT_TIMEOUT_MS == 1000


@pytest.mark.parametrize("missing", ["DATABASE_URL", "REDIS_URL"])
def test_missing_required_variable_names_it(valid_env, missing):
    valid_env.delenv(missing)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert missing in str(exc.value)
    assert exc.value.problems[0].startswith(missing)


def test_empty_string_counts_as_missing(valid_env):
    valid_env.setenv("DATABASE_URL", "")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "DATABASE_URL" in str(exc.value)


def test_every_missing_variable_is_named_not_just_the_first(clean_env):
    with pytest.raises(ConfigError) as exc:
        load_settings()
    msg = str(exc.value)
    assert "DATABASE_URL" in msg and "REDIS_URL" in msg


@pytest.mark.parametrize(
    "name,value",
    [
        ("API_PORT", "80"),  # privileged port: a non-root container cannot bind it
        ("API_PORT", "notaport"),
        ("LOG_LEVEL", "VERBOSE"),
        ("READINESS_CACHE_TTL_SECONDS", "-1"),
        ("SHUTDOWN_DRAIN_TIMEOUT_SECONDS", "0"),
        ("REDIS_COMMAND_TIMEOUT_MS", "0"),
        ("DATABASE_URL", "mysql://u:p@h/db"),
        ("REDIS_URL", "http://cache:6379"),
    ],
)
def test_invalid_value_is_rejected_naming_the_variable(valid_env, name, value):
    valid_env.setenv(name, value)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert name in str(exc.value)


def test_error_message_never_echoes_the_value(valid_env):
    # A DATABASE_URL carries a password. A boot error that prints it puts the secret in CloudWatch.
    valid_env.setenv("DATABASE_URL", "mysql://user:s3cr3t-pw@h/db")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "s3cr3t-pw" not in str(exc.value)


def test_process_exits_nonzero_with_json_line_naming_the_variable(tmp_path):
    """The real boot path, as a subprocess: no DATABASE_URL -> exit 78 and one JSON line on stdout."""
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "REDIS_URL")}
    env["REDIS_URL"] = "redis://cache.invalid:6379/0"
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "app", "api"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 78, (proc.returncode, proc.stdout, proc.stderr)
    lines = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    line = lines[0]
    assert line["level"] == "CRITICAL"
    assert "DATABASE_URL" in line["message"]
    assert line["missing_or_invalid"] == ["DATABASE_URL"]
    assert line["request_id"]  # every line carries one, even this one


def test_unknown_command_is_one_json_line_on_stdout_and_exits_64(tmp_path):
    """A typo in the task definition's command must leave a parseable line in CloudWatch, not plain stderr."""
    env = {k: v for k, v in os.environ.items()}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "app", "API"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    lines = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["level"] == "CRITICAL"
    assert lines[0]["command"] == "API"
    assert lines[0]["request_id"]
    assert proc.stderr == ""

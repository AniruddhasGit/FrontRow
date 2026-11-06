"""S-XCT-29 (PRD P-XCT-15, S7.9): every setting from the environment, and a non-zero exit at boot
when one is wrong. The ledger's AcceptanceCriteria cell is the spec; each test names its clause.

The WORKER half of "exit non-zero in both the api and the worker process" is the worker test beside the api one.
"""

from __future__ import annotations

import ast
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core import config as config_module
from app.core.config import CROSS_FIELD_CHECKS, ConfigError, Settings, load_settings

from ..conftest import VALID_ENV
from ._support import REPO, rg

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONFIG_PY = BACKEND_DIR / "app" / "core" / "config.py"
ENV_EXAMPLE = REPO / ".env.example"

THE_FIVE = ("DATABASE_URL", "REDIS_URL", "QUEUE_URL", "JWT_SECRET", "COOKIE_SECURE")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _boot_env(**overrides: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in Settings.model_fields}
    env.update(VALID_ENV)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    for k, v in overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def _boot(env: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )


def _refused(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return False
    except OSError:
        return True


def _boot_watching(env: dict[str, str], cwd: Path, port: int) -> tuple[subprocess.CompletedProcess, bool]:
    """Boot the api and probe its port WHILE it runs, not only after it has exited (a dead process can never
    hold a port, so a check made afterwards proves nothing). Returns the result and whether a connect to the
    port ever succeeded during boot. Sampling, so a bind shorter than one probe could still be missed; the
    absence of uvicorn's "running on" line is the second, independent signal."""
    proc = subprocess.Popen([sys.executable, "-m", "app", "api"], cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    bound = False
    for _ in range(3000):  # up to ~30 s of 10 ms waits
        bound = bound or not _refused(port)
        try:
            proc.wait(timeout=0.01)
            break
        except subprocess.TimeoutExpired:
            continue
    out, err = proc.communicate(timeout=30)
    result = subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    return result, bound or "running on" in out.lower()


# ---------------------------------------------------------------- the five with no default


@pytest.mark.parametrize("name", THE_FIVE)
def test_each_of_the_five_unset_exits_nonzero_naming_it_and_never_binds(name, tmp_path):
    port = _free_port()
    proc, bound = _boot_watching(_boot_env(**{name: None, "API_PORT": str(port)}), tmp_path, port)
    assert proc.returncode != 0, proc.stdout
    assert name in proc.stdout and name in proc.stderr
    assert not bound


@pytest.mark.parametrize("name", THE_FIVE)
def test_the_five_have_no_default(name):
    assert Settings.model_fields[name].is_required()
    # rg -n 'Field\(' backend/app/core/config.py shows no default for any of the five
    field_lines = [line for _, _, line in rg(r"Field\(", "backend/app/core/config.py")]
    assert not [ln for ln in field_lines if re.match(rf"\s*{name}\s*:", ln)]


def test_a_type_or_bound_failure_names_the_variable_and_the_bound(valid_env):
    valid_env.setenv("API_PORT", "80")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "API_PORT" in str(exc.value) and "1024" in str(exc.value)


# ---------------------------------------------------------------- the thirteen cross-field checks


def test_cross_field_checks_is_an_ordered_tuple_of_thirteen_named_entries():
    assert isinstance(CROSS_FIELD_CHECKS, tuple)
    assert len(CROSS_FIELD_CHECKS) == 13
    names = [c.name for c in CROSS_FIELD_CHECKS]
    assert all(names) and len(set(names)) == 13


def _refused_by_checks(env, **values: str) -> ConfigError:
    for k, v in values.items():
        env.setenv(k, v)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    return exc.value


def test_check1_payment_delay_against_the_hold(valid_env):
    valid_env.setenv("SEAT_HOLD_TTL_SECONDS", "180")
    valid_env.setenv("PAYMENT_SIMULATED_DELAY_MS", "1500")
    load_settings()
    err = _refused_by_checks(valid_env, PAYMENT_SIMULATED_DELAY_MS="200000")
    assert "PAYMENT_SIMULATED_DELAY_MS" in str(err)


@pytest.mark.parametrize("code", ["INR", "USD"])  # USD: SRC-006 CUR-1
def test_check2_minor_unit_ratio_other_than_100_with_inr_or_usd(valid_env, code):
    err = _refused_by_checks(valid_env, CURRENCY_CODE=code, CURRENCY_MINOR_UNIT_RATIO="1000")
    assert "CURRENCY_MINOR_UNIT_RATIO" in str(err)


def test_check3_timezone_must_resolve(valid_env):
    valid_env.setenv("CINEMA_TIMEZONE", "Asia/Kolkata")
    load_settings()
    err = _refused_by_checks(valid_env, CINEMA_TIMEZONE="Asia/Nowhere")
    assert "CINEMA_TIMEZONE" in str(err)


def test_check5_secure_cookie_over_plain_http(valid_env):
    err = _refused_by_checks(valid_env, COOKIE_SECURE="true", PUBLIC_BASE_URL="http://frontrow.example.invalid")
    assert "COOKIE_SECURE" in str(err)


@pytest.mark.parametrize(
    "api,worker", [("8000", "8000"), ("80", "8001"), ("70000", "8001"), ("8000", "80"), ("8000", "70000")]
)
def test_check12_ports_equal_or_out_of_range_exit_nonzero_in_the_api_process(api, worker, tmp_path):
    proc = _boot(_boot_env(API_PORT=api, WORKER_METRICS_PORT=worker), tmp_path)
    assert proc.returncode != 0, proc.stdout


@pytest.mark.parametrize(
    "api,worker", [("8000", "8000"), ("80", "8001"), ("70000", "8001"), ("8000", "80"), ("8000", "70000")]
)
def test_check12_ports_equal_or_out_of_range_exit_nonzero_in_the_worker_process(api, worker, tmp_path):
    # The worker half (Phase 5 added the worker): it loads the same settings and refuses the same values at boot.
    proc = subprocess.run([sys.executable, "-m", "app", "worker"], cwd=tmp_path,
                          env=_boot_env(API_PORT=api, WORKER_METRICS_PORT=worker), capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0, proc.stdout
    assert '"service": "worker"' in proc.stdout or '"service":"worker"' in proc.stdout


# ---------------------------------------------------------------- the boot log


def test_resolved_configuration_is_logged_exactly_once_with_secrets_redacted():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app", "api"],
        cwd=BACKEND_DIR,
        env=_boot_env(API_PORT=str(port)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        end = time.monotonic() + 20  # a startup deadline only; no assertion depends on the time
        while _refused(port) and time.monotonic() < end and proc.poll() is None:
            time.sleep(0.1)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
    lines = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    resolved = [ln for ln in lines if ln["message"] == "configuration resolved"]
    assert len(resolved) == 1, out
    shown = resolved[0]["settings"]
    assert set(shown) == set(Settings.model_fields)
    for name, value in shown.items():
        if re.search(r"SECRET|PASSWORD|TOKEN|URL", name):
            assert value == "[REDACTED]", name
    assert shown["PAYMENT_PROVIDER"] == "simulated"
    for secret in (VALID_ENV["JWT_SECRET"], VALID_ENV["DATABASE_URL"]):
        assert secret not in out


def test_no_environment_switch_anywhere_in_the_app():
    assert rg(r"ENVIRONMENT|APP_ENV|is_prod|if .*production", "backend/app") == []


# ---------------------------------------------------------------- .env.example and config.py


def _env_example_names() -> list[str]:
    return [ln.split("=", 1)[0] for ln in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines() if re.match(r"^[A-Z][A-Z0-9_]*=", ln)]


def test_settings_names_equal_env_example_names():
    # The API's settings model plus the seed's own variables, which the seed declares and nothing under
    # backend/app reads (S-XCT-48). The test's copy of that list must equal the seed's.
    from tests.conftest import SEED_VARIABLES
    from tests.seed.kit import seed

    assert seed.SEED_VARIABLES == SEED_VARIABLES
    declared = set(Settings.model_fields) | set(seed.SEED_VARIABLES)
    in_example = set(_env_example_names())
    assert declared == in_example, {"only_in_settings": declared - in_example, "only_in_env_example": in_example - declared}


def test_every_env_example_assignment_has_a_comment_line_directly_above():
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    bad = [lines[i] for i in range(len(lines)) if re.match(r"^[A-Z][A-Z0-9_]*=", lines[i]) and (i == 0 or not lines[i - 1].startswith("#"))]
    assert bad == []


def test_the_env_example_seed_password_is_refused_by_the_seed_placeholder_check(clean_env):
    from tests.seed.kit import seed

    value = next(ln.split("=", 1)[1] for ln in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines() if ln.startswith("SEED_DEFAULT_PASSWORD="))
    clean_env.setenv("SEED_DEFAULT_PASSWORD", value)
    clean_env.setenv("DATABASE_URL", "postgresql://nobody@db.invalid/none")
    with pytest.raises(seed.SeedError) as exc:
        seed.seed_inputs()
    assert "SEED_DEFAULT_PASSWORD" in str(exc.value) and "placeholder" in str(exc.value)
    assert value not in str(exc.value)


def test_env_example_holds_no_credential():
    assert rg(r"(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)", ".env.example") == []


def test_every_assignment_in_config_py_has_a_comment_line_directly_above():
    src = CONFIG_PY.read_text(encoding="utf-8")
    lines = src.splitlines()
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            above = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not above.startswith("#"):
                bad.append((node.lineno, lines[node.lineno - 1]))
    assert bad == []


def test_config_module_has_no_environment_name_switch():
    assert not hasattr(config_module, "ENVIRONMENT")

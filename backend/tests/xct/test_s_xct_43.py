"""S-XCT-43 (PRD P-XCT-29, OPEN-TLS-01): the deployed environment is never called production and holds only
seeded demonstration data; nothing is designed around the absence of TLS.

The TLS specification is resolved THROUGH the Spec cell of the docs/30 Deployment/AWS_PREP_QUEUE.md row whose
Item names the TLS certificate (row 14), as the criterion says, and then checked.
"""

from __future__ import annotations

import os
import subprocess
import sys

from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR
from tests.seed.kit import one, seeded  # noqa: F401
from tests.xct._support import DEPLOY, REPO, prep_queue, rg, spec_files, strip_md

DEPLOYED_PATHS = ("docs/30 Deployment", "backend/app", "backend/migrations", "frontend/src", "scripts",
                  "docker-compose.yml", ".env.example")


def test_nothing_names_or_configures_the_deployed_environment_as_production():
    assert (REPO / "frontend" / "src").is_dir() and (REPO / "scripts" / "seed.py").is_file()  # not vacuous
    assert rg(r"frontrow-prod|[-_]prod\b|ENV=prod|the production environment", *DEPLOYED_PATHS, ignore_case=True) == []


def _api(env_overrides: dict, drop: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({k: v for k, v in VALID_ENV.items() if k not in drop})
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-m", "app", "api"], cwd=BACKEND_DIR, env=env, capture_output=True,
                          text=True, timeout=60, stdin=subprocess.DEVNULL)


def test_cookie_secure_has_no_default_and_the_process_exits_without_it():
    lines = [ln for ln in (BACKEND_DIR / "app" / "core" / "config.py").read_text(encoding="utf-8").splitlines()
             if ln.strip().startswith("COOKIE_SECURE:")]
    assert lines == ["    COOKIE_SECURE: bool"]
    result = _api({}, drop=("COOKIE_SECURE",))
    assert result.returncode != 0
    assert "COOKIE_SECURE" in result.stdout + result.stderr


def test_cookie_secure_true_without_an_https_base_url_exits_naming_both():
    result = _api({"COOKIE_SECURE": "true", "PUBLIC_BASE_URL": "http://localhost:8080"})
    assert result.returncode != 0
    assert "COOKIE_SECURE" in result.stdout + result.stderr and "PUBLIC_BASE_URL" in result.stdout + result.stderr


def test_only_seeded_demonstration_data_is_loaded(seeded):
    db, _ = seeded
    assert one(db, "SELECT count(*) FROM movie") == 8
    assert one(db, "SELECT count(*) FROM movie WHERE title NOT LIKE 'DEMO %%'") == 0
    assert one(db, "SELECT count(*) FROM users WHERE email NOT LIKE '%%.invalid'") == 0


def test_no_token_rides_in_a_query_string_and_no_second_session_mechanism_exists():
    assert rg(r"\?token=|access_token=|Authorization: Bearer", "backend/app", "frontend/src") == []
    assert rg(r"localStorage", "frontend/src") == []


def test_no_self_made_certificate_and_no_key_material_in_the_tree():
    assert rg(r"self-signed|openssl req", "backend/app", "backend/migrations", "frontend/src", "scripts",
              "docker-compose.yml", "docs/30 Deployment", ignore_case=True) == []
    # By FILENAME, walking the tree (a superset of git ls-files: untracked files count too, which is stricter).
    named = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "dist", "__pycache__", ".venv", "venv"}]
        named += [os.path.join(root, f) for f in files if f.endswith((".pem", ".crt", ".key"))]
    assert named == []


def test_the_tls_specification_carries_the_five_steps_and_the_zone_c_sentence():
    spec = (DEPLOY / "P2_TLS_CERTIFICATE.md").read_text(encoding="utf-8")
    for step in ("request an ACM certificate validated by DNS", "add an HTTPS listener redirecting HTTP to it",
                 "set COOKIE_SECURE=true", "verify the domain in SES with DKIM and SPF",
                 "set PUBLIC_BASE_URL to the HTTPS address"):
        assert step in spec, step
    assert "The first three steps are Zone C. No application code changes." in spec


def test_the_tls_spec_is_found_through_the_queue_rows_spec_cell():
    (row,) = [r for r in prep_queue() if "TLS certificate" in strip_md(r["Item"])]
    assert [DEPLOY / f for f in spec_files(row["Spec"])] == [DEPLOY / "P2_TLS_CERTIFICATE.md"]


def test_rg_fails_on_a_path_that_does_not_exist():
    # A zero-hits sweep over a moved or mistyped tree must fail, never pass vacuously (verifier, round 3).
    import pytest

    with pytest.raises(FileNotFoundError):
        rg("anything", "backend/no-such-tree")

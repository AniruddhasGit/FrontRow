"""S-XCT-37 (PRD P-XCT-23): no service or dependency outside the approved list.

The allowlist below is the recorded one. Adding a package means adding it here, in the same change,
with the source that approves it - which is the review point the criterion exists to force.
"""

from __future__ import annotations

import json
import re

from ._support import DEPLOY, REPO, prep_queue, rg, spec_files, strip_md

# name -> why it is approved. SRC-002 §4 fixes the stack; each entry is part of it.
PYTHON_ALLOWLIST = {
    "fastapi": "SRC-002 §4 backend framework",
    "uvicorn": "the ASGI server FastAPI runs on",
    "pydantic-settings": "PRD S7.9: the validation layer of a library already in the stack",
    "redis": "SRC-002 §4 Redis client",
    "psycopg": "SRC-002 §4 PostgreSQL driver",
    "sqlalchemy": "SRC-002 §4 / AGENT_CONTRACT: the ORM Alembic needs (Phase 2)",
    "alembic": "SRC-002 §4 migrations (Phase 2)",
    "boto3": "SRC-002 §4: S3, SQS, SES clients (Phase 5)",
    "bcrypt": "PRD P-XCT-06 password hashing",
    "pyjwt": "SRC-002 §4 own JWT auth",
    "pytest": "test only",
    "httpx": "test only: the HTTP client the tests drive the API with",
}
JS_ALLOWLIST = {
    "react": "SRC-002 §4 frontend",
    "react-dom": "SRC-002 §4 frontend",
    "@types/react": "TypeScript types for React",
    "@types/react-dom": "TypeScript types for React DOM",
    "@vitejs/plugin-react": "SRC-002 §4 Vite's React plugin",
    "typescript": "SRC-002 §4 TypeScript",
    "vite": "SRC-002 §4 Vite",
}
FORBIDDEN_JS = ("@mui", "@chakra-ui", "antd", "bootstrap", "react-bootstrap", "tailwindcss", "styled-components", "@emotion")


def _python_packages() -> set[str]:
    names = set()
    for req in ("backend/requirements.txt", "backend/requirements-dev.txt"):
        for line in (REPO / req).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                names.add(re.split(r"[\[=<>~! ]", line, 1)[0].lower())
    return names


def _js_packages() -> set[str]:
    pkg = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    return set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))


def test_no_task_queue_library_and_no_argon2():
    assert rg(r"^(rq|dramatiq|celery|huey|argon2|argon2-cffi|passlib\[argon2\])\b", "backend/requirements.txt", ignore_case=True) == []


def test_no_component_library_css_framework_or_css_in_js():
    bad = [p for p in _js_packages() if any(p == f or p.startswith(f + "/") for f in FORBIDDEN_JS)]
    assert bad == []


def test_every_package_is_on_the_recorded_allowlist():
    assert _python_packages() - set(PYTHON_ALLOWLIST) == set()
    assert _js_packages() - set(JS_ALLOWLIST) == set()


def test_forbidden_services_appear_only_where_they_are_called_forbidden():
    pattern = r"eks|fargate|nat gateway|secretsmanager|secrets manager|managed grafana|opensearch|cloudfront|bastion|vpc interface endpoint"
    hits = rg(pattern, "backend/app", "backend/migrations", "frontend/src", "docs/30 Deployment", ignore_case=True)
    assert [h for h in hits if "forbidden" not in h[2].lower()] == []


def test_no_local_aws_imitations_and_the_resulting_gap_is_stated():
    assert rg(r"minio|mailhog", "docker-compose.yml", ignore_case=True) == []
    assert rg(
        "local development does not fully exercise the poster upload path without AWS credentials and does not exercise SES at all",
        "docs/30 Deployment",
        fixed=True,
    )


def test_the_specification_names_exactly_the_ten_services():
    rows = [r for r in prep_queue() if "ECS cluster" in strip_md(r["Item"])]
    assert len(rows) == 1
    text = (DEPLOY / spec_files(rows[0]["Spec"])[0]).read_text(encoding="utf-8").splitlines()
    i = text.index("## Services this product uses")
    items = []
    for line in text[i + 1 :]:
        if line.startswith("#"):
            break
        if line.startswith("- "):
            items.append(line[2:].strip())
    assert set(items) == {
        "ECS on EC2",
        "Application Load Balancer",
        "RDS PostgreSQL",
        "ElastiCache Redis",
        "SQS",
        "SES",
        "S3",
        "SSM Parameter Store",
        "ECR",
        "CloudWatch Logs",
    }
    assert len(items) == 10

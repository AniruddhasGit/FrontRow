"""Verifier fixes on the error envelope, the engine and the migration URL (Phase 2 integration).

- a framework HTTPException is mapped to the registry code for its status, never to INTERNAL_ERROR on a 4xx;
- the engine hides statement parameters, so a driver error logged with exc_info never carries row values;
- migrations/env.py builds its URL with app/db's one function, not a second string rewrite.
"""

from __future__ import annotations

import ast

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.db import async_url, make_engine
from app.main import create_app
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR
from tests.test_health import ok_probe


@pytest.mark.parametrize("status,code", [(400, "REQUEST_INVALID"), (401, "AUTH_REQUIRED"), (403, "FORBIDDEN"),
                                         (404, "NOT_FOUND"), (413, "REQUEST_INVALID"), (500, "INTERNAL_ERROR"),
                                         (503, "INTERNAL_ERROR")])
def test_a_framework_http_exception_carries_the_registry_code_for_its_status(valid_env, clock, status, code):
    application = create_app(Settings(**VALID_ENV), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])

    @application.get("/_test/raise")
    async def raise_it():
        raise StarletteHTTPException(status_code=status)

    with TestClient(application, raise_server_exceptions=False) as c:
        r = c.get("/_test/raise")
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    if status < 500:
        assert r.json()["error"]["request_id"] not in r.json()["error"]["message"]  # only a 5xx quotes the id


def test_the_engine_hides_statement_parameters(valid_env):
    assert make_engine(Settings(**VALID_ENV)).sync_engine.hide_parameters is True


@pytest.mark.parametrize("raw,expected", [
    ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
    ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
    # a password containing the scheme text is not rewritten: only the prefix is
    ("postgresql://u:postgres://x@h/d", "postgresql+psycopg://u:postgres://x@h/d"),
])
def test_the_driver_url_rewrites_only_the_scheme(raw, expected):
    assert async_url(raw) == expected


def test_migrations_env_uses_the_applications_url_function_and_no_string_rewrite():
    source = (BACKEND_DIR / "migrations" / "env.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "app.db"]
    assert imports and any(a.name == "async_url" for n in imports for a in n.names)
    assert ".replace(" not in source

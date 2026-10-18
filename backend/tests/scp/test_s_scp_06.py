"""S-SCP-06 - the role set is exactly four and no cinema-staff role exists (P-SCP-10, SRC-003 C-1).

The Role enum is the account lane's (E-ACC). This test finds it wherever it is defined under app/
rather than guessing a module path, and fails - never skips - while it does not exist.
"""

from __future__ import annotations

import enum
import importlib
import os
import pkgutil
import re

import pydantic
from fastapi.testclient import TestClient

import app
from app.main import create_app
from tests.dbkit import app_settings, owner_sql
from tests.test_health import ok_probe
from tests.xct._support import rg


def _modules():
    for info in pkgutil.walk_packages(app.__path__, "app."):
        yield importlib.import_module(info.name)


def _role_enums() -> list[type[enum.Enum]]:
    found = {}
    for module in _modules():
        candidate = getattr(module, "Role", None)
        if isinstance(candidate, type) and issubclass(candidate, enum.Enum):
            found[candidate] = None
    return list(found)


def test_the_role_enum_has_exactly_the_four_values():
    enums = _role_enums()
    assert len(enums) == 1, f"expected one Role enum under app/, found {enums}"
    role = enums[0]
    assert sorted(member.value for member in role) == ["admin", "customer", "guest", "manager"]
    assert len(role) == 4
    assert not [m.name for m in role if re.search(r"staff|usher|door|gate|scanner|attendant", m.name, re.I)]


def test_no_staff_or_scanner_vocabulary_in_the_code():
    assert rg(r"cinema_?staff|door_?scanner|ticket_?validat", "backend/app", "frontend/src", ignore_case=True) == []


def test_no_request_model_declares_a_role_field():
    offenders = []
    for module in _modules():
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, pydantic.BaseModel) and value.__module__ == module.__name__:
                if "role" in value.model_fields:
                    offenders.append(f"{module.__name__}.{value.__name__}")
    assert offenders == []


def test_register_with_a_role_property_creates_a_customer(migrated_db, clock):
    # Registration rate-limits through Redis (the account lane's); a database number of its own.
    redis_url = re.sub(r"/\d+$", "/14", os.environ["TEST_REDIS_URL"])
    app_ = create_app(app_settings(migrated_db, REDIS_URL=redis_url), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    before = owner_sql(migrated_db, "SELECT count(*) FROM users")
    with TestClient(app_) as client:
        r = client.post("/api/auth/register", json={"email": "staff@example.invalid", "password": "long enough pw", "role": "staff"})
    assert r.status_code == 201  # the role is never read from the body (EP-ACC-01)
    assert owner_sql(migrated_db, "SELECT count(*) FROM users")[0][0] == before[0][0] + 1
    assert owner_sql(migrated_db, "SELECT role FROM users WHERE email = 'staff@example.invalid'") == [("customer",)]

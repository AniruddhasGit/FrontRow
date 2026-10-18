"""S-XCT-13 - the session rides in an HttpOnly, SameSite=Lax cookie, Secure from configuration.

Covered: the cookie's attributes on both COOKIE_SECURE settings (set by app/core/security.py, the one
function the sign-in handler will call), COOKIE_SECURE's missing-at-boot and cross-field refusals, and
the localStorage / SameSite=None scans over backend/app and frontend/src. NOT covered: a real sign-in
response (EP-ACC-02), the GET-mutates-nothing walk (no product GET route exists yet), and the
sessionStorage 'fr.selection' clause (the seat lane's frontend).
"""

from __future__ import annotations

import re
from http.cookies import SimpleCookie
from pathlib import Path

import pytest
from starlette.responses import Response

from app.core.config import ConfigError, Settings, load_settings
from app.core.security import SESSION_COOKIE, clear_session_cookie, set_session_cookie
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR

FRONTEND_SRC = BACKEND_DIR.parent / "frontend" / "src"


def _set_cookie(secure: str, base_url: str = "http://localhost:8080") -> tuple[str, SimpleCookie]:
    settings = Settings(**{**VALID_ENV, "COOKIE_SECURE": secure, "PUBLIC_BASE_URL": base_url})
    response = Response()
    set_session_cookie(response, "header.payload.signature", settings)
    header = response.headers["set-cookie"]
    jar = SimpleCookie()
    jar.load(header)
    return header, jar


@pytest.mark.parametrize("secure,base", [("false", "http://localhost:8080"), ("true", "https://frontrow.example.invalid")])
def test_the_cookie_carries_httponly_lax_path_max_age_and_secure_iff_configured(secure, base):
    header, jar = _set_cookie(secure, base)
    morsel = jar[SESSION_COOKIE]
    attrs = {a.strip().split("=")[0].lower(): (a.strip().split("=", 1) + [""])[1] for a in header.split(";")[1:]}
    assert morsel.value == "header.payload.signature"
    assert "httponly" in attrs
    assert attrs["samesite"].lower() == "lax"
    assert attrs["path"] == "/"
    assert attrs["max-age"] == "43200"  # SESSION_TTL_SECONDS default
    assert ("secure" in attrs) is (secure == "true")


def test_clearing_the_cookie_repeats_the_attributes_with_max_age_zero():
    response = Response()
    clear_session_cookie(response, Settings(**VALID_ENV))
    header = response.headers["set-cookie"].lower()
    assert header.startswith(f"{SESSION_COOKIE}=") and "max-age=0" in header and "httponly" in header and "samesite=lax" in header


def test_cookie_secure_has_no_default_and_its_absence_names_it(valid_env):
    valid_env.delenv("COOKIE_SECURE")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "COOKIE_SECURE" in exc.value.names


def test_cookie_secure_true_without_https_is_refused_naming_both(valid_env):
    valid_env.setenv("COOKIE_SECURE", "true")
    valid_env.setenv("PUBLIC_BASE_URL", "http://frontrow.example.invalid")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert {"COOKIE_SECURE", "PUBLIC_BASE_URL"} <= set(exc.value.names)


def _scan(root: Path, pattern: str, flags: int = 0) -> list[str]:
    rx = re.compile(pattern, flags)
    return [
        f"{p}:{i}"
        for p in root.rglob("*")
        if p.is_file() and p.suffix in (".py", ".ts", ".tsx", ".js", ".css", ".html") and "__pycache__" not in p.parts
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if rx.search(line)
    ]


def test_frontend_source_is_mounted_so_the_scans_below_are_not_vacuous():
    assert (FRONTEND_SRC / "main.tsx").is_file(), f"{FRONTEND_SRC} not mounted - run through the compose test service"


def test_no_localstorage_in_the_frontend():
    assert _scan(FRONTEND_SRC, r"localStorage") == []


def test_samesite_none_appears_in_neither_application_tree():
    pattern = r"samesite=none|samesite: *.none."
    assert _scan(BACKEND_DIR / "app", pattern, re.IGNORECASE) == []
    assert _scan(FRONTEND_SRC, pattern, re.IGNORECASE) == []

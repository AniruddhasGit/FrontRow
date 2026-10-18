"""PUBLIC router at /api/auth: register, sign in, sign out (EP-ACC-01..03). No session dependency.

Owned by the account lane; created empty by the foundation lane so main.py never needs editing.
Password reset (EP-ACC-05/06) ships in Phase 5 (SRC-004 JC-R6-02) - only its tables exist in Phase 2.

Each limited handler spends its rate-limit tokens FIRST, before it validates anything, so every
request is counted - a malformed one included (P-XCT-07). The bodies are permissive models (every
field optional, unknown fields ignored) because the published 422 sentences are the account rows'
own (P-ACC-01, P-ACC-02), and because a `role` in the body must be ignored, never obeyed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import db, get_clock, get_settings
from app.api.errors import ApiError
from app.core import ratelimit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import clear_session_cookie, issue_session_token, set_session_cookie
from app.domain import accounts

router = APIRouter(prefix="/api/auth")


class Credentials(BaseModel):
    # Any, not str: pydantic would refuse {"email": 1} with a 422 BEFORE the handler runs, and that request
    # would never be counted by the limiter (P-XCT-07 "every request counted"). The domain checks the type.
    email: Any = None
    password: Any = None


def _start_session(response: Response, user: dict, settings: Settings, clock: Clock) -> dict:
    token = issue_session_token(user_id=user["id"], role=user["role"], password_version=user["password_version"],
                                now=clock.now(), settings=settings)
    set_session_cookie(response, token, settings)
    return accounts.identity(user["id"], user["email"], user["role"])


@router.post("/register", status_code=201)
async def register(body: Credentials, request: Request, response: Response, conn: AsyncConnection = Depends(db),
                   settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> dict:
    ip = ratelimit.client_ip(request, settings)
    await ratelimit.enforce(request, [(ratelimit.REGISTER_IP, ip)], accounts.UNAVAILABLE_REGISTER)
    email = accounts.checked_email(body.email)
    password = accounts.check_new_password(body.password, settings.PASSWORD_MIN_LENGTH)
    user = await accounts.register(conn, request.app.state, settings, email, password)
    return _start_session(response, user, settings, clock)


@router.post("/login")
async def login(body: Credentials, request: Request, response: Response, conn: AsyncConnection = Depends(db),
                settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> dict:
    key = body.email.strip().lower() if isinstance(body.email, str) else ""
    checks = [(ratelimit.LOGIN_EMAIL, key)] if key else []
    checks.append((ratelimit.LOGIN_IP, ratelimit.client_ip(request, settings)))
    await ratelimit.enforce(request, checks, accounts.UNAVAILABLE_SIGN_IN)
    if not key or not isinstance(body.password, str) or not body.password:
        raise ApiError(422, "VALIDATION_FAILED", "Enter your email address and password.")
    # Shape only - never the password rules: an older account may hold a password today's rules refuse.
    email = accounts.checked_email(body.email)
    user = await accounts.sign_in(conn, request.app.state, settings, email, body.password, clock.now())
    return _start_session(response, user, settings, clock)


@router.post("/logout", status_code=204)
async def logout(settings: Settings = Depends(get_settings)) -> Response:
    # Public on purpose (P-ACC-05): an HttpOnly cookie that is expired or malformed can only be
    # cleared by the server, so this never answers 401.
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response

"""PUBLIC router at /api/auth: register, sign in, sign out (EP-ACC-01..03). No session dependency.

Owned by the account lane; created empty by the foundation lane so main.py never needs editing.
Password reset request and confirm (EP-ACC-05/06, P-ACC-07/08) are the last two routes.

Each limited handler spends its rate-limit tokens FIRST, before it validates anything, so every
request is counted - a malformed one included (P-XCT-07). The bodies are permissive models (every
field optional, unknown fields ignored) because the published 422 sentences are the account rows'
own (P-ACC-01, P-ACC-02), and because a `role` in the body must be ignored, never obeyed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import db, get_clock, get_settings
from app.api.errors import ApiError
from app.core import ratelimit
from app.core.clock import Clock
from app.core.config import Settings
from app.core.logging import get_request_id
from app.core.security import clear_session_cookie, issue_session_token, set_session_cookie
from app.domain import accounts
from app.domain import booking as bk

log = logging.getLogger("app.accounts")
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
    # Hashed: the per-user sign-in bucket is keyed on a submitted address, which must not sit in Redis in the clear.
    checks = [(ratelimit.LOGIN_EMAIL, hashlib.sha256(key.encode("utf-8")).hexdigest())] if key else []
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


class ResetRequest(BaseModel):
    email: Any = None


class ResetConfirm(BaseModel):
    # Exactly these two properties (S-ACC-08): no old_password field exists, and one sent anyway is ignored.
    token: Any = None
    password: Any = None


async def _send_reset(app: Any, settings: Settings, clock: Clock, outbox_id: int, message: Any, queue: Any) -> None:
    """After the response: bounded like the receipt's fast path. NOT retried on failure (SRC-004 JC-R6-01): nothing
    stored can rebuild the token, the outbox row stays pending, and the customer - who saw the same 202 - asks
    again. Its own connection: the request's connection is already back in the pool. The log line names the outbox
    row, never the token or the address."""
    try:
        await asyncio.wait_for(queue(message), timeout=settings.QUEUE_SEND_TIMEOUT_MS / 1000)
        async with app.state.db_engine.connect() as conn:
            await bk.mark_sent(conn, outbox_id, clock.now())
    except Exception:  # noqa: BLE001 - the 202 was owed whatever the queue did
        log.warning("password reset queue send failed; not retried", extra={"outbox_id": outbox_id})


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(body: ResetRequest, request: Request, background: BackgroundTasks,
                                 conn: AsyncConnection = Depends(db),
                                 settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> dict:
    """EP-ACC-05. The same 202 body for a known and an unknown address (P-ACC-07 rows 1-2) - and the same timing:
    the queue send runs after the response, so a known address is not betrayed by the wait on the queue.
    ponytail: the token + outbox INSERT for a known address is still a few ms the unknown path does not spend;
    closing that too needs a constant-time pad, upgrade path if the timing ever matters at that resolution."""
    await ratelimit.enforce(request, [(ratelimit.RESET_REQUEST_IP, ratelimit.client_ip(request, settings))], accounts.RESET_UNAVAILABLE)
    email = accounts.reset_email(body.email)
    issued = await accounts.request_reset(conn, settings, email, clock.now(), get_request_id())
    queue = getattr(request.app.state, "reset_queue", None)
    if issued is not None and queue is not None:
        outbox_id, message = issued
        background.add_task(_send_reset, request.app, settings, clock, outbox_id, message, queue)
    return {"message": accounts.reset_sent(settings)}


@router.post("/password-reset/confirm")
async def password_reset_confirm(body: ResetConfirm, request: Request, response: Response,
                                 settings: Settings = Depends(get_settings), clock: Clock = Depends(get_clock)) -> dict:
    """EP-ACC-06. The bucket first - every request spends a token, a malformed one included (P-ACC-08 row 8) - then the
    43-character check, which reads no database."""
    await ratelimit.enforce(request, [(ratelimit.RESET_CONFIRM_IP, ratelimit.client_ip(request, settings))], accounts.RESET_UNAVAILABLE)
    token = accounts.reset_token(body.token)
    # The connection is opened only now, not by the `db` dependency, which connects before the handler runs: a
    # malformed token must reach no database at all (S-ACC-08), not even a pool checkout.
    async with request.app.state.db_engine.connect() as conn:
        user = await accounts.confirm_reset(conn, request.app.state, settings, token, body.password, clock.now())
    return _start_session(response, user, settings, clock)

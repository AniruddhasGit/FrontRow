"""Accounts: the rules and the database work behind register and sign-in (P-ACC-01..03, P-ACC-05).

app/api/auth.py is the HTTP surface and calls these. Every published sentence lives here, with the
figure it quotes rendered from configuration (PASSWORD_MIN_LENGTH) or from the input (the byte
count) - never typed in. 72 is bcrypt's truncation point and is the one deliberate literal
(security.PASSWORD_MAX_BYTES).

bcrypt is ~300 ms of CPU, so it always runs in a worker thread, at most BCRYPT_THREAD_POOL_SIZE at a
time, and a request that waits past BCRYPT_HASH_TIMEOUT_MS is answered 503 (P-ACC-03 exception 3).
The functions are looked up on the `security` module at call time, so a test can wrap them.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

import anyio
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core import security
from app.core.config import Settings
from app.models import users

log = logging.getLogger("app.accounts")

EMAIL_MAX_CHARS = 254
UNAVAILABLE_SIGN_IN = "Sign-in is unavailable right now. Browsing still works. Try again shortly."
UNAVAILABLE_REGISTER = "Registration is unavailable right now. Browsing still works. Try again shortly."
CREDENTIALS_INVALID = "That email address and password do not match an account."
ALREADY_REGISTERED = ("An account already exists for that email address. Sign in instead, or reset the password "
                      "if you have forgotten it.")
_UNIQUE_EMAIL = "uq_users__email_ci"


def _invalid(message: str, field: str, **details: Any) -> ApiError:
    return ApiError(422, "VALIDATION_FAILED", message, {"field": field, **details})


def checked_email(raw: str | None) -> str:
    """Trimmed and shape-checked (P-ACC-01 rows 1-3). Case is kept as entered; nothing else is mapped."""
    email = (raw or "").strip()
    if not email:
        raise _invalid("Enter an email address.", "email")
    if len(email) > EMAIL_MAX_CHARS:
        raise _invalid("That email address is too long. The limit is 254 characters.", "email")
    local, _, domain = email.partition("@")
    if len(email) < 3 or email.count("@") != 1 or not local or "." not in domain or any(c.isspace() for c in email):
        raise _invalid("That is not a valid email address.", "email")
    return email


def check_new_password(password: str | None, min_length: int) -> str:
    """P-ACC-01 rows 4-6 / P-ACC-03. Never trimmed. Characters for the floor, BYTES for the ceiling."""
    if not password:
        raise _invalid("Enter a password.", "password")
    if len(password) < min_length:
        raise _invalid(f"Your password must be at least {min_length} characters. It does not have to contain "
                       "numbers or symbols.", "password")
    size = len(password.encode("utf-8"))
    if size > security.PASSWORD_MAX_BYTES:
        raise _invalid(f"Your password is too long. The limit is {security.PASSWORD_MAX_BYTES} bytes and yours is {size}. "
                       "Most characters count as one byte; accented and non-Latin characters count as two, three or four.",
                       "password", byte_length=size)
    return password


def unusable_password_hash(cost: int) -> str:
    """P-ACC-01: a real bcrypt hash of 32 fresh CSPRNG bytes, discarded at once. Drawn PER ROW, so no two
    no-password accounts share a value. For E6 P-ADM-17's manager accounts. Synchronous: run it in a thread."""
    return security.hash_password(secrets.token_urlsafe(32), cost)


async def _bcrypt(state: Any, settings: Settings, unavailable: str, fn_name: str, *args: Any) -> Any:
    limiter = getattr(state, "bcrypt_limiter", None)
    if limiter is None:
        limiter = state.bcrypt_limiter = anyio.CapacityLimiter(settings.BCRYPT_THREAD_POOL_SIZE)
    try:
        with anyio.fail_after(settings.BCRYPT_HASH_TIMEOUT_MS / 1000):
            return await anyio.to_thread.run_sync(getattr(security, fn_name), *args, limiter=limiter, abandon_on_cancel=True)
    except TimeoutError:
        # A capacity signal, not a fault (P-ACC-03 exception 3).
        log.warning("bcrypt wait exceeded", extra={"timeout_ms": settings.BCRYPT_HASH_TIMEOUT_MS,
                                                   "pool_size": settings.BCRYPT_THREAD_POOL_SIZE})
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", unavailable) from None


def identity(user_id: int, email: str, role: str) -> dict[str, Any]:
    """The {user_id, email, role} body of EP-ACC-01/02/04 - exactly these three keys (S-ACC-06)."""
    return {"user_id": user_id, "email": email, "role": role}


def identity_of(user: Any) -> dict[str, Any]:
    """identity() of the dependency's CurrentUser (app/api/deps.py)."""
    return identity(user.id, user.email, user.role)


async def register(conn: AsyncConnection, state: Any, settings: Settings, email: str, password: str) -> dict[str, Any]:
    """Insert one customer row (P-ACC-01). The unique index on lower(email) is the guard; the read
    first only spares a bcrypt call for the common case."""
    taken = (await conn.execute(select(users.c.id).where(func.lower(users.c.email) == email.lower()))).first()
    await conn.rollback()
    if taken is not None:
        raise ApiError(409, "EMAIL_ALREADY_REGISTERED", ALREADY_REGISTERED)
    password_hash = await _bcrypt(state, settings, UNAVAILABLE_REGISTER, "hash_password", password, settings.BCRYPT_COST)
    try:
        async with conn.begin():
            user_id = (await conn.execute(
                insert(users).values(email=email, password_hash=password_hash, role="customer", password_version=1)
                .returning(users.c.id))).scalar_one()
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == _UNIQUE_EMAIL:
            raise ApiError(409, "EMAIL_ALREADY_REGISTERED", ALREADY_REGISTERED) from None  # a simultaneous twin won
        raise
    return {"id": user_id, "email": email, "role": "customer", "password_version": 1}


async def sign_in(conn: AsyncConnection, state: Any, settings: Settings, email: str, password: str, now) -> dict[str, Any]:
    """P-ACC-02. Exactly one bcrypt verification on every branch - a found row, an unknown address,
    an account whose hash is unusable - so the two failures cost the same and look the same."""
    row = (await conn.execute(
        select(users.c.id, users.c.email, users.c.password_hash, users.c.role, users.c.password_version)
        .where(func.lower(users.c.email) == email.lower()))).first()
    await conn.rollback()  # no transaction stays open across the bcrypt wait
    stored = row.password_hash if row is not None else None
    ok = await _bcrypt(state, settings, UNAVAILABLE_SIGN_IN, "verify_password", password, stored, settings.BCRYPT_COST)
    if not ok or row is None:
        raise ApiError(401, "CREDENTIALS_INVALID", CREDENTIALS_INVALID)
    async with conn.begin():
        # The one write on the sign-in path, and not an audit row: signing in is not a privileged write.
        await conn.execute(update(users).where(users.c.id == row.id).values(last_signed_in_at=now))
    return {"id": row.id, "email": row.email, "role": row.role, "password_version": row.password_version}

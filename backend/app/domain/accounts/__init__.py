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

import enum
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

import anyio
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core import security
from app.core.config import Settings
from app.domain.booking import MESSAGE_VERSION  # the one version the worker accepts, for both topics
from app.models import outbox_message, password_reset_token, users

log = logging.getLogger("app.accounts")


class Role(enum.StrEnum):
    """The four roles (SRC-003 C-1, PROVISIONAL; P-SCP-10). guest is the absence of a session and is never a
    stored value; users.role holds one of the other three. There is no staff or door-scanner role."""

    GUEST = "guest"
    CUSTOMER = "customer"
    MANAGER = "manager"
    ADMIN = "admin"


EMAIL_MAX_CHARS = 254
UNAVAILABLE_SIGN_IN = "Sign-in is unavailable right now. Browsing still works. Try again shortly."
UNAVAILABLE_REGISTER = "Registration is unavailable right now. Browsing still works. Try again shortly."
CREDENTIALS_INVALID = "That email address and password do not match an account."
ALREADY_REGISTERED = ("An account already exists for that email address. Sign in instead, or reset the password "
                      "if you have forgotten it.")
_UNIQUE_EMAIL = "uq_users__email_ci"


def _invalid(message: str, field: str, **details: Any) -> ApiError:
    return ApiError(422, "VALIDATION_FAILED", message, {"field": field, **details})


def checked_email(raw: Any) -> str:
    """Trimmed and shape-checked (P-ACC-01 rows 1-3). Case is kept as entered; nothing else is mapped.
    A value that is not a JSON string is not an email address at all: row 3's sentence."""
    if raw is not None and not isinstance(raw, str):
        raise _invalid("That is not a valid email address.", "email")
    email = (raw or "").strip()
    if not email:
        raise _invalid("Enter an email address.", "email")
    if len(email) > EMAIL_MAX_CHARS:
        raise _invalid("That email address is too long. The limit is 254 characters.", "email")
    local, _, domain = email.partition("@")
    if len(email) < 3 or email.count("@") != 1 or not local or "." not in domain or any(c.isspace() for c in email):
        raise _invalid("That is not a valid email address.", "email")
    return email


def check_new_password(password: Any, min_length: int) -> str:
    """P-ACC-01 rows 4-6 / P-ACC-03. Never trimmed. Characters for the floor, BYTES for the ceiling.
    A value that is not a JSON string carries no password text: row 4's "Enter a password."."""
    if not isinstance(password, str) or not password:
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
                insert(users).values(email=email, password_hash=password_hash, role=Role.CUSTOMER.value, password_version=1)
                .returning(users.c.id))).scalar_one()
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == _UNIQUE_EMAIL:
            raise ApiError(409, "EMAIL_ALREADY_REGISTERED", ALREADY_REGISTERED) from None  # a simultaneous twin won
        raise
    return {"id": user_id, "email": email, "role": Role.CUSTOMER.value, "password_version": 1}


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


# ---- password reset (P-ACC-07 / P-ACC-08, EP-ACC-05 / EP-ACC-06) ----------------------------------------------------

RESET_UNAVAILABLE = "Password reset is unavailable right now. Try again shortly."
RESET_NOT_VALID = "That reset link is not valid. Request a new one."
RESET_USED = "That reset link has already been used. Request a new one."
RESET_EXPIRED = "That reset link has expired. Request a new one."
RESET_TOPIC = "password_reset.send"
_TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")  # 32 bytes, URL-safe base64, unpadded


def reset_sent(settings: Settings) -> str:
    """The one shared sentence (P-ACC-07 rows 1-2): the minutes are PASSWORD_RESET_TTL_SECONDS // 60, never typed."""
    return ("If that email address has an account, a reset link is on its way to it. "
            f"The link works once and expires in {settings.PASSWORD_RESET_TTL_SECONDS // 60} minutes.")


def new_reset_token() -> str:
    """32 bytes from the CSPRNG, 43 URL-safe characters (P-ACC-07 step 4). Looked up at call time so a test can stub it.
    Shortening this or swapping `secrets` out is the one change no functional test catches; the confirm bucket is the
    control that survives it (P-ACC-08 row 8)."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def reset_email(raw: Any) -> str:
    """P-ACC-07 row 3: every shape failure - empty, too long, not an address - reads 'Enter an email address.'"""
    try:
        return checked_email(raw)
    except ApiError:
        raise _invalid("Enter an email address.", "email") from None


def reset_token(raw: Any) -> str:
    """P-ACC-08 row 4: anything but exactly 43 URL-safe characters is 422 with no database read."""
    if not isinstance(raw, str) or not _TOKEN_SHAPE.fullmatch(raw):
        raise _invalid(RESET_NOT_VALID, "token")
    return raw


async def request_reset(conn: AsyncConnection, settings: Settings, email: str, now: datetime,
                        request_id: str) -> tuple[int, dict[str, Any]] | None:
    """P-ACC-07 steps 1-6, one transaction. None for an unknown address (nothing written). Otherwise (outbox id, the
    queue body): the outbox payload carries NO token; the queue body is that payload plus the token (SRC-004 R-3)."""
    async with conn.begin():
        user_id = (await conn.execute(select(users.c.id).where(func.lower(users.c.email) == email.lower()))).scalar()
        if user_id is None:
            return None
        # Step 3: at most one live token per account.
        await conn.execute(update(password_reset_token).where(password_reset_token.c.user_id == user_id,
                                                              password_reset_token.c.used_at.is_(None)).values(used_at=now))
        token = new_reset_token()
        token_id = (await conn.execute(insert(password_reset_token).values(
            user_id=user_id, token_sha256=token_digest(token), created_at=now,
            expires_at=now + timedelta(seconds=settings.PASSWORD_RESET_TTL_SECONDS)).returning(password_reset_token.c.id))).scalar_one()
        payload = {"message_version": MESSAGE_VERSION, "request_id": request_id, "reset_token_id": token_id, "user_id": user_id}
        outbox_id = (await conn.execute(insert(outbox_message).values(
            topic=RESET_TOPIC, payload=payload, status="pending", attempts=0, created_at=now).returning(outbox_message.c.id))).scalar_one()
    return outbox_id, {**payload, "reset_token": token}


async def confirm_reset(conn: AsyncConnection, state: Any, settings: Settings, token: str, password: Any,
                        now: datetime) -> dict[str, Any]:
    """P-ACC-08. The single-use guarantee is the conditional UPDATE inside the transaction, never the read before it."""
    row = (await conn.execute(select(password_reset_token.c.id, password_reset_token.c.user_id, password_reset_token.c.expires_at,
                                     password_reset_token.c.used_at)
                              .where(password_reset_token.c.token_sha256 == token_digest(token)))).first()
    await conn.rollback()  # no transaction stays open across the bcrypt wait
    if row is None:
        raise ApiError(400, "RESET_TOKEN_INVALID", RESET_NOT_VALID)
    if row.used_at is not None:
        raise ApiError(400, "RESET_TOKEN_INVALID", RESET_USED)
    if now >= row.expires_at:
        raise ApiError(400, "RESET_TOKEN_INVALID", RESET_EXPIRED)
    password = check_new_password(password, settings.PASSWORD_MIN_LENGTH)
    password_hash = await _bcrypt(state, settings, RESET_UNAVAILABLE, "hash_password", password, settings.BCRYPT_COST)
    async with conn.begin():
        spent = await conn.execute(update(password_reset_token).where(password_reset_token.c.id == row.id,
                                                                      password_reset_token.c.used_at.is_(None)).values(used_at=now))
        if spent.rowcount != 1:
            raise ApiError(400, "RESET_TOKEN_INVALID", RESET_USED)  # lost the race (row 7): the block rolls back
        # password_version + 1 is what ends every older session: deps.current_user refuses a token whose pv differs.
        user = (await conn.execute(update(users).where(users.c.id == row.user_id).values(
            password_hash=password_hash, password_version=users.c.password_version + 1, last_signed_in_at=now)
            .returning(users.c.id, users.c.email, users.c.role, users.c.password_version))).one()
    return {"id": user.id, "email": user.email, "role": user.role, "password_version": user.password_version}

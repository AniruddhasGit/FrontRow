"""Credentials and the session token (P-XCT-06, P-ACC-03, P-ACC-05, FR-ADR-050).

EVERYTHING HERE IS SYNCHRONOUS ON PURPOSE. bcrypt is ~300 ms of pure CPU at cost 12; called from a
coroutine on the event loop it stalls every other request on the worker. Callers run hash_password / verify_password
in a thread (anyio's to_thread.run_sync with a BCRYPT_THREAD_POOL_SIZE limiter), never on the loop.

Nothing in this module logs, returns or stores a plaintext password.
"""

from __future__ import annotations

import functools
import secrets
from datetime import datetime, timedelta

import bcrypt
import jwt
from starlette.responses import Response

from app.core.config import Settings

SESSION_COOKIE = "fr_session"
# bcrypt reads at most 72 BYTES and silently ignores the rest, so two different long passwords would
# authenticate the same account. Fixed by the algorithm - not configuration (S7.9).
PASSWORD_MAX_BYTES = 72
_ALGORITHM = "HS256"  # P-ACC-05


class InvalidSession(Exception):
    """The token is malformed, unsigned by us, or missing a claim."""


class ExpiredSession(InvalidSession):
    """The token verified but its exp is not after the injected `now`."""


def password_problem(password: str, min_length: int) -> str | None:
    """The 422 message for an unacceptable password, or None. The floor is CHARACTERS, the ceiling BYTES."""
    if len(password) < min_length:
        return f"Use a password of at least {min_length} characters."
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return "Use a password of 72 bytes or fewer. Some characters count as more than one byte."
    return None


def hash_password(password: str, cost: int) -> str:
    # bcrypt 5 raises on > 72 bytes rather than truncating; password_problem() refuses it first with
    # the product's own message, so this is a second line, not the check.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=cost)).decode("ascii")


@functools.cache
def _dummy_hash(cost: int) -> bytes:
    # A real hash of a random value, made once per cost: comparing against it costs exactly what a real
    # comparison costs, so the response time does not disclose whether the email has an account.
    return bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt(rounds=cost))


def verify_password(password: str, password_hash: str | None, cost: int) -> bool:
    """True only for the right password. With password_hash=None (unknown email) it still runs one
    full bcrypt comparison, against a dummy hash, and returns False."""
    candidate = password.encode("utf-8")
    if len(candidate) > PASSWORD_MAX_BYTES:
        candidate = candidate[:PASSWORD_MAX_BYTES]  # cannot match: registration refuses such passwords
        password_hash = None
    target = password_hash.encode("ascii") if password_hash is not None else _dummy_hash(cost)
    ok = bcrypt.checkpw(candidate, target)
    return ok and password_hash is not None


def issue_session_token(*, user_id: int, role: str, password_version: int, now: datetime, settings: Settings) -> str:
    """Claims are sub, role, pv, iat, exp and nothing else (P-ACC-05): a JWT is readable by anyone who
    holds it. `now` is injected; the token never reads the wall clock."""
    claims = {
        "sub": str(user_id),
        "role": role,
        "pv": password_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.SESSION_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_session_token(token: str, *, now: datetime, settings: Settings) -> dict:
    """The verified claims, or InvalidSession / ExpiredSession. Expiry is checked against the injected
    `now`, not PyJWT's own clock, so a test can move time."""
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[_ALGORITHM],  # a fixed list: never trust the token's own `alg` header
            # EVERY claim is required (P-ACC-05): an absent claim is a refusal, never read as a default.
            options={"verify_exp": False, "verify_iat": False, "require": ["sub", "role", "pv", "iat", "exp"]},
        )
        user_id = int(claims["sub"])
        pv = int(claims["pv"])
        exp = int(claims["exp"])
        int(claims["iat"])
        if not isinstance(claims["role"], str):
            raise TypeError("role")
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidSession() from exc
    if now.timestamp() >= exp:
        raise ExpiredSession()
    return {"user_id": user_id, "pv": pv, "exp": exp, "role": claims.get("role")}


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        # Explicit Max-Age, equal to the JWT's lifetime: without it the cookie dies with the browser.
        max_age=settings.SESSION_TTL_SECONDS,
        path="/",
        # HttpOnly: a script on the page cannot read the session (why it is not in localStorage).
        httponly=True,
        # Lax is the product's ONLY cross-site request defence (P-XCT-06). Never relax it.
        samesite="lax",
        # From configuration (OPEN-TLS-01 deferred). True without TLS = nobody stays signed in.
        secure=settings.COOKIE_SECURE,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Max-Age=0 with the SAME attributes it was issued with - a cookie is only cleared by a match.

    Written by hand, not with set_cookie(): the standard library renders an empty value as `""`, and
    P-ACC-05 publishes `fr_session=; Max-Age=0`. Same attribute order and spelling as set_session_cookie."""
    response.headers.append(
        "set-cookie",
        f"{SESSION_COOKIE}=; HttpOnly; Max-Age=0; Path=/; SameSite=lax" + ("; Secure" if settings.COOKIE_SECURE else ""),
    )

"""Structured logging: JSON, one object per line, to STDOUT, never a file (SRC-002 §5.4.5, §7.6).

PRD P-XCT-12 / S7.8 fixes the field set on every line:
    timestamp (UTC ISO-8601) . level . logger . message . request_id . service . instance_id
plus, where they apply, route . method . status_code . duration_ms . client_request_id . ...

REQUEST ID. Eight lowercase hex characters we generate; an inbound X-Request-Id is never trusted
(see app/core/request_context.py). A line written OUTSIDE any request - boot, shutdown - carries the
process LIFECYCLE id instead: one id generated when the process starts, so every line still has a
request_id and all of one process's boot and shutdown lines can be found with one search.

REDACTION is central, applied by the formatter to every record, so forgetting at one call site does
not leak (P-XCT-12 exception 5). Field names on the denylist are replaced, and credentials embedded in
a URL inside a message are scrubbed.

Why stdout and not a file: a file is state on a stateless container and dies with it. Something
outside the container must collect stdout - on ECS that is the awslogs driver, which is Zone C and
is a Phase 1 prep-queue row. Without it, every line this module writes is lost on restart.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import re
import secrets
import sys
import traceback
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import IO, Any

# Generated once per process. See module docstring.
LIFECYCLE_ID = secrets.token_hex(4)

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default=LIFECYCLE_ID)


def new_request_id() -> str:
    """Eight hex characters from a CSPRNG (P-XCT-12). A correlation aid, NEVER a key: it collides."""
    return secrets.token_hex(4)


def get_request_id() -> str:
    return _request_id.get()


@contextlib.contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


# Matched case-insensitively against extra-field names. Never logged at any level (PRD S7.8).
# R-3 (SRC-004): the password-reset token rides in a queue payload from Phase 5, so `token`,
# `reset_token` and `payload` are on the list from the first line.
# No card names: no card field exists anywhere (SRC-003 OPEN-PAY-01, S-PAY-10, S-SCP-12), so an entry for one would be
# the only card-shaped name in the application.
DENYLIST = frozenset(
    {
        "password",
        "password_hash",
        "new_password",
        "secret",
        "jwt",
        "jwt_secret",
        "token",
        "access_token",
        "reset_token",
        "authorization",
        "cookie",
        "set_cookie",
        "session",
        "database_url",
        "redis_url",
        "payload",
    }
)
REDACTED = "[REDACTED]"

# scheme://user:password@host  ->  scheme://user:***@host
_URL_CREDENTIALS = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/@\s]*):([^@\s]+)@")

# Attributes every LogRecord has. Anything else on a record arrived through `extra=` and is emitted
# as a field.
# `color_message` is uvicorn's ANSI-coloured duplicate of its own message: escape-code noise in a log
# store, and a second copy of every uvicorn line.
_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "color_message"}


# A JSON Web Token anywhere in a string: three base64url segments, the first a JSON header ("eyJ" is '{"').
# The session cookie is one; so is anything a client pastes into X-Request-Id, which is logged as
# client_request_id. Without this a token sent in any header we record reaches CloudWatch verbatim.
_JWT_SHAPED = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
# Nested extras are walked this deep; anything deeper is stringified and scrubbed (a cycle cannot recurse forever).
_MAX_DEPTH = 8


def scrub(text: str) -> str:
    return _JWT_SHAPED.sub(REDACTED, _URL_CREDENTIALS.sub(r"\1:***@", text))


def _clean(key: str, value: Any, depth: int = 0) -> Any:
    """Redaction for one extra field, applied at every depth: a denylisted key at any level of a nested dict
    or list is replaced, and every string is scrubbed (P-XCT-12 exception 5)."""
    if key.lower() in DENYLIST:
        return REDACTED
    if isinstance(value, str):
        return scrub(value)
    if depth >= _MAX_DEPTH and isinstance(value, (dict, list, tuple)):
        return scrub(str(value))
    if isinstance(value, dict):
        return {k: _clean(str(k), v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean("", v, depth + 1) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, instance_id: str, now: Callable[[], datetime]) -> None:
        super().__init__()
        self.service = service
        self.instance_id = instance_id
        self.now = now  # injected: tests pass a fake clock, production passes SystemClock().now

    def format(self, record: logging.LogRecord) -> str:
        ts = self.now().astimezone(timezone.utc)
        out: dict[str, Any] = {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": scrub(record.getMessage()),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
            "service": self.service,
            "instance_id": self.instance_id,
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key in out or key.startswith("_"):
                continue
            # Without the scrub, a driver error passed as extra={"error": str(exc)} prints the DB password.
            out[key] = _clean(key, value)
        if record.exc_info:
            # The trace goes in the log and never in the response (P-XCT-11).
            out["exc_info"] = scrub("".join(traceback.format_exception(*record.exc_info)))
        # default=str: a non-JSON value (a datetime, an exception) is stringified rather than making
        # the log call itself raise - a logging failure must never become a request failure.
        return json.dumps(out, default=str, separators=(",", ":"))


def configure_logging(
    level: str,
    service: str,
    instance_id: str,
    now: Callable[[], datetime],
    stream: IO[str] | None = None,
) -> None:
    """Route every logger in the process - ours, uvicorn's, the libraries' - through one JSON handler.

    Without taking over uvicorn's loggers, its startup and shutdown lines are plain text and every
    "pipe the logs through a JSON parser" check fails on the first line.
    """
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(service=service, instance_id=instance_id, now=now))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # uvicorn's own access log is OFF (server.py passes access_log=False): it is one plain line per
    # request with no request id. Our middleware writes the one completion line per request instead.
    logging.getLogger("uvicorn.access").disabled = True


def emit_fatal(message: str, now: Callable[[], datetime], also_stderr: bool = False, **fields: Any) -> None:
    """One JSON line for a failure that happens BEFORE logging can be configured (bad config)."""
    ts = now().astimezone(timezone.utc)
    line = {
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
        "level": "CRITICAL",
        "logger": "app.boot",
        "message": scrub(message),
        "request_id": LIFECYCLE_ID,
        "service": "api",
        "instance_id": None,
        **fields,
    }
    text = json.dumps(line, default=str, separators=(",", ":")) + "\n"
    sys.stdout.write(text)
    sys.stdout.flush()
    # The same line on stderr when the caller asks: a person running the container by hand reads
    # stderr, and the config-failure path must name the variable there (S-XCT-29, S-SCP-03).
    if also_stderr:
        sys.stderr.write(text)
        sys.stderr.flush()

"""The one error envelope every failure uses (PRD P-XCT-11, FR-ADR-052, SCR-XCT-01).

    {"error": {"code": "...", "message": "...", "details": {}, "request_id": "a1b2c3d4"}}

The interface branches on `code`, never on `message`. A handler or dependency raises ApiError; the
handlers below render it. Unhandled exceptions are rendered as INTERNAL_ERROR by the last-resort
catch in app/core/request_context.py, which already owns the request id and the stack-trace log line.

MESSAGES holds the registry's LAST-RESORT sentences. A P-row that publishes its own wording for its
own surface passes it as ApiError(message=...) - that row owns its words (SCR-XCT-01).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id

# {request_id} is filled in at render time; INTERNAL_ERROR is the only code whose sentence quotes it
# (P-XCT-11 exception 1 - the id is shown to the customer on 5xx only).
MESSAGES = {
    "INTERNAL_ERROR": "The server could not complete this request. If you need help, quote {request_id}.",
    "NOT_FOUND": "That page does not exist.",
    "METHOD_NOT_ALLOWED": "That action is not available. Nothing was changed.",
    "AUTH_REQUIRED": "Sign in to continue.",
    "FORBIDDEN": "This account does not have access to that page.",
    "VALIDATION_FAILED": "Some fields need attention.",
    "REQUEST_INVALID": "That request could not be read and nothing was changed. Reload the page and try again.",
}


class ApiError(Exception):
    """A failure with a registry code. Raise it from a dependency or a handler; never build a response."""

    def __init__(self, status: int, code: str, message: str | None = None, details: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        # Response headers the failure carries, e.g. Retry-After on a 429 (SRC-002 §8.4.2).
        self.headers = headers
        super().__init__(code)


def envelope(code: str, request_id: str, details: dict[str, Any] | None = None, message: str | None = None) -> dict[str, Any]:
    text = message if message is not None else MESSAGES[code]
    return {"error": {"code": code, "message": text.format(request_id=request_id), "details": details or {}, "request_id": request_id}}


def _respond(status: int, code: str, details: dict[str, Any] | None = None, message: str | None = None, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(envelope(code, get_request_id(), details, message), status_code=status, headers=headers)


# A framework HTTPException's status -> the registry code it is answered with (405 has its own handler).
_HTTP_CODES = {401: "AUTH_REQUIRED", 403: "FORBIDDEN", 404: "NOT_FOUND"}


def install_error_handlers(app: FastAPI) -> None:
    """Mounted on the APPLICATION, never on a router (P-XCT-11 3a): routing has already failed when
    404 and 405 are raised, so a router-level handler would never see them."""

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _respond(exc.status, exc.code, exc.details, exc.message, exc.headers)

    @app.exception_handler(405)
    async def method_not_allowed(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # The path exists for another method. Generic and entity-blind by necessity: the path is only a
        # string here. Keeps the framework's Allow header, which names the methods that do exist.
        return _respond(405, "METHOD_NOT_ALLOWED", headers=getattr(exc, "headers", None))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Without this the framework answers with its own {"detail": ...} body, a second shape the
        # interface cannot parse. In practice: 404 for an address no method serves. Each status gets the
        # registry code for it; any other 4xx is a request the server could not read (REQUEST_INVALID),
        # and only a 5xx is INTERNAL_ERROR - the one code whose sentence quotes the request id.
        code = _HTTP_CODES.get(exc.status_code) or ("INTERNAL_ERROR" if exc.status_code >= 500 else "REQUEST_INVALID")
        return _respond(exc.status_code, code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_failed(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Replaces FastAPI's default 422 body, which would break the contract on exactly the errors a
        # form hits most (P-XCT-11 precondition). A body that does not parse at all is REQUEST_INVALID.
        errors = exc.errors()
        first = errors[0] if errors else {}
        if first.get("type") == "json_invalid":
            return _respond(400, "REQUEST_INVALID")
        loc = [str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path", "header", "cookie")]
        return _respond(422, "VALIDATION_FAILED", {"field": ".".join(loc)} if loc else {})

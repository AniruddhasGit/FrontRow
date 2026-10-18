"""The one error envelope every failure uses (PRD P-XCT-11, FR-ADR-052).

    {"error": {"code": "...", "message": "...", "details": {}, "request_id": "a1b2c3d4"}}

The interface branches on `code`, never on `message`. Phase 1 can only produce the three codes below;
later phases add theirs to this registry. Messages are the PRD's literal strings.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id

MESSAGES = {
    "INTERNAL_ERROR": "The server could not complete this request.",
    "NOT_FOUND": "That page does not exist.",
    "METHOD_NOT_ALLOWED": "That action is not available. Nothing was changed.",
}

_STATUS_TO_CODE = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def envelope(code: str, request_id: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": MESSAGES[code], "details": details or {}, "request_id": request_id}}


def install_error_handlers(app: FastAPI) -> None:
    async def http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Without this handler the framework answers 404/405 with its own {"detail": ...} body, a
        # second shape the interface cannot parse. 405 is a global handler, not a route (P-XCT-11 3a).
        code = _STATUS_TO_CODE.get(exc.status_code, "INTERNAL_ERROR")
        return JSONResponse(envelope(code, get_request_id()), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    app.add_exception_handler(StarletteHTTPException, http_exception)  # type: ignore[arg-type]

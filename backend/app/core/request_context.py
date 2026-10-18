"""Request id, one completion line per request, and the last-resort 500  (PRD P-XCT-11, P-XCT-12).

A plain ASGI middleware rather than Starlette's BaseHTTPMiddleware, because BaseHTTPMiddleware runs
the endpoint in a separate task and the request-id context variable would not reliably reach it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.clock import Clock
from app.api.errors import envelope
from app.core.logging import bind_request_id, new_request_id

log = logging.getLogger("app.request")

# Polled continuously by the load balancer and the container runtime. Logging every success would
# dominate the log volume and the 5 GB CloudWatch allowance (PRD S7.8). Failures are still logged,
# by the readiness module and by the >= 400 rule below.
QUIET_PATHS = frozenset({"/health/live", "/health/ready"})

# The route TEMPLATE ("/movies/{id}"), never the raw path. A request that matched no route gets this
# constant: without it every scanner probe URL lands verbatim in the log and the route field becomes
# unbounded, so "requests per route" stops being a query anyone can run.
UNMATCHED = "<unmatched>"


def _route(scope: dict) -> str:
    return getattr(scope.get("route"), "path", None) or UNMATCHED


class RequestContextMiddleware:
    def __init__(self, app: Any, clock: Clock) -> None:
        self.app = app
        self.clock = clock

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()  # ALWAYS ours. An inbound header is recorded, never used.
        client_request_id = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                client_request_id = value.decode("latin-1")[:128]
                break

        started = self.clock.monotonic()
        state = {"status": 500, "started": False}

        async def send_with_id(message: dict) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["started"] = True
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"x-request-id"]
                # The contract's content type is `application/json; charset=utf-8` on every JSON
                # response (contract.json conventions). Starlette adds a charset only to text/* types,
                # so it is added here once rather than in every response class.
                headers = [(k, b"application/json; charset=utf-8") if k.lower() == b"content-type" and v == b"application/json" else (k, v) for k, v in headers]
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        with bind_request_id(request_id):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:  # noqa: BLE001 - the last line of defence; nothing gets past it
                # The trace goes to the log, never to the response (P-XCT-11 exception 1).
                log.error("unhandled exception", exc_info=True, extra={"route": _route(scope)})
                if not state["started"]:
                    body = json.dumps(envelope("INTERNAL_ERROR", request_id)).encode()
                    await send_with_id(
                        {
                            "type": "http.response.start",
                            "status": 500,
                            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                        }
                    )
                    await send_with_id({"type": "http.response.body", "body": body})
            finally:
                path = scope.get("path", "")
                route = _route(scope)
                status = state["status"]
                # Quiet means SUCCESSFUL polls only. A 503 from readiness, or a 405 from someone
                # POSTing to a health path, is not a routine poll and stays visible.
                if path not in QUIET_PATHS or status >= 400:
                    fields: dict[str, Any] = {
                        "route": route,
                        "method": scope.get("method"),
                        "status_code": status,
                        "duration_ms": round((self.clock.monotonic() - started) * 1000),
                    }
                    if client_request_id is not None:
                        fields["client_request_id"] = client_request_id
                    log.info("request completed", extra=fields)

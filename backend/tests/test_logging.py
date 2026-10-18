"""P-XCT-12 / SRC-002 §7.6 and P-XCT-11: JSON to stdout, a request id we generate, one envelope."""

from __future__ import annotations

import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import bind_request_id, get_request_id
from app.main import create_app

from .conftest import VALID_ENV
from .test_health import failing_probe, ok_probe

REQUIRED_FIELDS = {"timestamp", "level", "logger", "message", "request_id", "service", "instance_id"}
RID = re.compile(r"^[0-9a-f]{8}$")


@pytest.fixture
def app(valid_env, clock):
    application = create_app(Settings(**VALID_ENV), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])

    @application.get("/_test/hello")
    async def hello():
        logging.getLogger("app.test").info("inside the handler", extra={"booking_id": 9008})
        return {"hello": "world"}

    @application.get("/_test/boom")
    async def boom():
        raise RuntimeError("kaboom detail that must stay in the log")

    @application.get("/_test/slow")
    async def slow():
        clock.advance(0.812)
        return {}

    return application


def test_every_line_is_json_with_the_fixed_field_set(app, log_capture):
    with TestClient(app) as c:
        c.get("/_test/hello")
    lines = log_capture.lines()
    assert lines, "nothing was logged at all - a vacuous pass is not a pass"
    for line in lines:
        missing = REQUIRED_FIELDS - line.keys()
        assert not missing, (missing, line)
        assert line["service"] == "api"
        assert line["instance_id"] == "test0001"


def test_timestamp_is_utc_iso8601_from_the_injected_clock(app, log_capture):
    with TestClient(app) as c:
        c.get("/_test/hello")
    assert log_capture.lines()[0]["timestamp"] == "2026-10-18T09:30:00.123Z"


def test_request_id_is_generated_returned_and_on_every_line_of_that_request(app, log_capture):
    with TestClient(app) as c:
        r = c.get("/_test/hello")
    rid = r.headers["x-request-id"]
    assert RID.match(rid)
    request_lines = [ln for ln in log_capture.lines() if ln["request_id"] == rid]
    messages = [ln["message"] for ln in request_lines]
    assert "inside the handler" in messages
    assert "request completed" in messages
    handler_line = next(ln for ln in request_lines if ln["message"] == "inside the handler")
    assert handler_line["booking_id"] == 9008


def test_two_requests_get_two_different_ids(app, log_capture):
    with TestClient(app) as c:
        a = c.get("/_test/hello").headers["x-request-id"]
        b = c.get("/_test/hello").headers["x-request-id"]
    assert a != b


def test_inbound_request_id_is_never_trusted(app, log_capture):
    with TestClient(app) as c:
        r = c.get("/_test/hello", headers={"X-Request-Id": "forged-id-from-the-internet"})
    assert r.headers["x-request-id"] != "forged-id-from-the-internet"
    assert RID.match(r.headers["x-request-id"])
    done = next(ln for ln in log_capture.lines() if ln["message"] == "request completed")
    assert done["client_request_id"] == "forged-id-from-the-internet"
    assert done["request_id"] == r.headers["x-request-id"]


def test_one_completion_line_with_route_status_and_duration(app, log_capture):
    with TestClient(app) as c:
        c.get("/_test/slow")
    done = [ln for ln in log_capture.lines() if ln["message"] == "request completed"]
    assert len(done) == 1
    assert done[0]["route"] == "/_test/slow"
    assert done[0]["method"] == "GET"
    assert done[0]["status_code"] == 200
    assert done[0]["duration_ms"] == 812  # from the injected clock, not the wall clock
    assert done[0]["level"] == "INFO"


def test_successful_health_polls_are_not_logged_at_info(app, log_capture):
    with TestClient(app) as c:
        log_capture.stream.truncate(0)
        log_capture.stream.seek(0)
        c.get("/health/live")
        c.get("/health/ready")
    assert [ln for ln in log_capture.lines() if ln.get("route", "").startswith("/health")] == []


def test_a_failed_readiness_poll_is_logged(valid_env, clock, log_capture):
    application = create_app(Settings(**VALID_ENV), clock=clock, probes=[failing_probe("postgres"), ok_probe("redis")])
    with TestClient(application) as c:
        c.get("/health/ready")
    warn = [ln for ln in log_capture.lines() if ln["level"] == "WARNING"]
    assert any(ln.get("checks", {}).get("postgres") == "unreachable" for ln in warn)


def test_unhandled_exception_is_500_envelope_and_trace_stays_in_the_log(app, log_capture):
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/_test/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"] == r.headers["x-request-id"]
    assert "kaboom" not in r.text and "Traceback" not in r.text and "RuntimeError" not in r.text
    err = [ln for ln in log_capture.lines() if ln["level"] == "ERROR"]
    assert len(err) == 1
    assert err[0]["request_id"] == r.headers["x-request-id"]
    assert "kaboom" in err[0]["exc_info"]


def test_unknown_path_is_404_envelope(app, log_capture):
    with TestClient(app) as c:
        r = c.get("/no/such/thing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]


def test_wrong_method_is_405_envelope(app, log_capture):
    with TestClient(app) as c:
        r = c.post("/health/live")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_denylisted_fields_are_redacted_centrally(log_capture):
    log = logging.getLogger("app.test")
    log.info("login attempt", extra={"password": "hunter2", "authorization": "Bearer abc.def", "user_id": 7})
    line = log_capture.lines()[-1]
    assert line["password"] == "[REDACTED]"
    assert line["authorization"] == "[REDACTED]"
    assert line["user_id"] == 7
    assert "hunter2" not in log_capture.stream.getvalue()


def test_credentials_inside_a_url_in_a_message_are_scrubbed(log_capture):
    logging.getLogger("app.test").warning("could not reach postgresql://frontrow:pa55word@db:5432/x")
    raw = log_capture.raw_lines()[-1]
    assert "pa55word" not in raw
    assert "postgresql://frontrow:***@db:5432/x" in raw


def test_credentials_inside_a_url_in_an_extra_field_are_scrubbed(log_capture):
    logging.getLogger("app.test").warning("probe failed", extra={"error": "connect postgresql://u:hunter2@h/db failed"})
    raw = log_capture.raw_lines()[-1]
    assert "hunter2" not in raw
    assert "postgresql://u:***@h/db" in raw


def test_lines_outside_a_request_carry_the_process_lifecycle_id(log_capture):
    logging.getLogger("app.test").info("boot line")
    line = log_capture.lines()[-1]
    assert RID.match(line["request_id"])
    assert line["request_id"] == get_request_id()


def test_bind_request_id_scopes_and_restores(log_capture):
    outer = get_request_id()
    with bind_request_id("abcdef01"):
        assert get_request_id() == "abcdef01"
    assert get_request_id() == outer


def test_a_non_poll_request_to_a_health_path_is_still_logged(app, log_capture):
    """Only SUCCESSFUL polls are quiet. A 405 on a health path is not a poll and must be visible."""
    with TestClient(app) as c:
        c.post("/health/live")
    done = [ln for ln in log_capture.lines() if ln["message"] == "request completed"]
    assert [(d["route"], d["status_code"]) for d in done] == [("/health/live", 405)]


def test_uvicorn_color_message_is_dropped(log_capture):
    """uvicorn attaches an ANSI-coloured duplicate of its message; in CloudWatch it is escape-code noise."""
    logging.getLogger("uvicorn.error").info("Started server process [%d]", 1, extra={"color_message": "\x1b[36m%d\x1b[0m"})
    line = log_capture.lines()[-1]
    assert "color_message" not in line
    assert line["message"] == "Started server process [1]"


def test_an_unmatched_path_logs_a_constant_route_not_the_raw_path(app, log_capture):
    """A raw path is unbounded cardinality, and a scanner's probe URL would land verbatim in the log."""
    with TestClient(app) as c:
        c.get("/wp-admin/../../etc/passwd?token=abc")
    done = [ln for ln in log_capture.lines() if ln["message"] == "request completed"]
    assert [(d["route"], d["status_code"]) for d in done] == [("<unmatched>", 404)]

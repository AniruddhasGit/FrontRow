"""S-XCT-25 (P-XCT-12): the confirm's request id travels through the outbox and the queue into the worker's receipt job.

End to end against ONE ElasticMQ queue: the real API (in-process, the real SqsQueue fast path) confirms a booking, and
the real worker (`python -m app worker`, a subprocess, the real SqsQueue receive) sends its receipt through the stub
transport. Each run creates its own uniquely named queue. Every request id is read off the 201's X-Request-Id header
at assertion time and is never compared to a literal."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import uuid

import pytest

from app.core.logging import configure_logging
from app.workers import receipt_port
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR, run_migrate
from tests.pay.kit import F7, api, clock_at, confirm, hold, owner_sql, user, world7
from tests.xct._support import rg

pytestmark = pytest.mark.anyio


def _queue_url() -> str:
    import boto3

    endpoint = os.environ.get("TEST_QUEUE_ENDPOINT")
    if not endpoint:
        pytest.fail("TEST_QUEUE_ENDPOINT is not set: run the suite with `docker compose --profile test run --rm test`", pytrace=False)
    sqs = boto3.client("sqs", region_name=VALID_ENV["AWS_REGION"], endpoint_url=endpoint)
    url = sqs.create_queue(QueueName=f"xct25-{uuid.uuid4().hex[:12]}")["QueueUrl"]
    # The URL ElasticMQ hands back names its own host setting; the path is what identifies the queue.
    return endpoint + "/" + url.split("/", 3)[3]


def _worker_lines(db, queue_url: str, until: str) -> list[dict]:
    env = {k: v for k, v in os.environ.items() if k not in VALID_ENV}
    env.update({**VALID_ENV, "DATABASE_URL": db.app_url, "QUEUE_URL": queue_url, "QUEUE_POLL_WAIT_SECONDS": "1",
                "PYTHONPATH": str(BACKEND_DIR)})
    proc = subprocess.Popen([sys.executable, "-m", "app", "worker"], cwd=BACKEND_DIR, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    lines: list[dict] = []
    try:
        end = time.monotonic() + 60  # a deadline for the subprocess only; no assertion depends on the time
        while time.monotonic() < end:
            raw = proc.stdout.readline()
            if not raw:
                break
            lines.append(json.loads(raw))
            if lines[-1].get("message") == until:
                break
        proc.send_signal(signal.SIGTERM)
        rest, _ = proc.communicate(timeout=60)
        lines += [json.loads(ln) for ln in rest.splitlines() if ln.strip()]
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, lines
    return lines


async def test_the_request_id_reaches_the_worker_line_through_the_outbox_and_the_queue(migrated_db):
    db = migrated_db
    world7(db)
    owner_sql(db, "ALTER TABLE booking ALTER COLUMN id RESTART WITH 9008")
    queue_url = _queue_url()
    u = user(db)
    stream = io.StringIO()
    configure_logging(level="INFO", service="api", instance_id="test0001", now=clock_at().now, stream=stream)
    try:
        async with api(db, clock_at(), QUEUE_URL=queue_url) as c:
            state = c.application.state
            state.receipt_queue = receipt_port(state, c.settings, c.clock)
            h = await hold(c, u, [F7])
            r = await confirm(c, u, h["hold_token"])
    finally:
        logging.getLogger().handlers.clear()
    assert r.status_code == 201, r.text
    rid = r.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{8}", rid)
    b = r.json()["booking_id"]
    assert b == 9008
    assert owner_sql(db, "SELECT payload->>'request_id', status FROM outbox_message WHERE (payload->>'booking_id')::bigint = %s", (b,)) == [
        (rid, "sent")]

    worker_lines = [ln for ln in _worker_lines(db, queue_url, "receipt sent") if ln.get("request_id") == rid]
    sent = [ln for ln in worker_lines if ln.get("message") == "receipt sent"]
    assert len(sent) == 1, worker_lines
    assert sent[0]["service"] == "worker" and sent[0]["job_id"] and sent[0]["booking_id"] == 9008
    assert owner_sql(db, "SELECT status FROM receipt_dispatch WHERE booking_id = %s", (b,)) == [("sent",)]
    # The API half last, so a red here still shows the worker half above held.
    api_lines = [json.loads(ln) for ln in stream.getvalue().splitlines() if rid in ln]
    assert any(ln.get("service") == "api" and ln.get("route") == "/api/bookings" and ln.get("status_code") == 201
               and ln.get("booking_id") == 9008 for ln in api_lines), api_lines


def test_the_migrate_command_logs_json_lines_carrying_service_migrate(migrated_db):
    out = run_migrate(migrated_db.owner_url)
    assert out.returncode == 0, out.stderr
    lines = [json.loads(ln) for ln in out.stdout.splitlines() if ln.strip()]
    assert lines and all(ln["service"] == "migrate" for ln in lines)


def test_the_log_driver_row_and_the_crash_loop_sentence_exist():
    from tests.xct._support import prep_queue, strip_md

    assert [r for r in prep_queue() if "awslogs" in r["Item"] and strip_md(r["Needed by"]).strip() == "Phase 1"]
    assert rg("the record of a crash loop is destroyed by the restart that caused it", "docs/30 Deployment", fixed=True)

"""S-TKT-06 (P-TKT-04): the outbox relay sends what the fast path left behind, on the worker's own loop, against the
injected clock; the boot check keeps the fast-path bound inside the drain; nothing schedules anything.

The fast-path clauses (the confirm's bounded send, its ERROR line) are the confirm handler's, app/api/bookings.py."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.config import ConfigError, load_settings
from tests.tkt.kit import Clock, Queue, booking, owner_sql, truncate, worker

pytestmark = pytest.mark.anyio
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def db(migrated_db):
    truncate(migrated_db)
    return migrated_db


def _outbox(db, b, created_at):
    payload = '{"booking_id": %d, "dispatch_seq": 1, "request_id": "a1b2c3d4", "message_version": 1}' % b
    return owner_sql(db, "INSERT INTO outbox_message (topic, payload, status, attempts, created_at) "
                         "VALUES ('receipt.send', %s::jsonb, 'pending', 0, %s) RETURNING id", (payload, created_at))[0][0]


@pytest.mark.parametrize("after,relayed", [(29, 0), (31, 1)])
async def test_the_relay_selects_by_the_injected_clocks_age(db, after, relayed):
    clock = Clock()
    b = booking(db)
    o = _outbox(db, b, clock.now())
    clock.advance(after)
    w = worker(db, clock, OUTBOX_RELAY_MIN_AGE_SECONDS="30")
    try:
        assert await w.relay() == relayed
    finally:
        await w.engine.dispose()
    status, sent_at = owner_sql(db, "SELECT status, sent_at FROM outbox_message WHERE id = %s", (o,))[0]
    assert len(w.queue.sent) == relayed
    if relayed:
        assert status == "sent" and sent_at == clock.now() and w.queue.sent[0][0] == "receipt.send"
        # The relay marks the outbox row; the dispatch row is the worker's claim's, and stays pending.
        assert owner_sql(db, "SELECT status FROM receipt_dispatch WHERE booking_id = %s", (b,)) == [("pending",)]
    else:
        assert status == "pending" and sent_at is None


async def test_an_unreachable_queue_leaves_the_row_pending_and_counts_the_attempt(db):
    clock = Clock()
    o = _outbox(db, booking(db), clock.now() - timedelta(minutes=5))
    q = Queue()
    q.fail = True
    w = worker(db, clock, queue=q)
    try:
        assert await w.relay() == 0
    finally:
        await w.engine.dispose()
    assert owner_sql(db, "SELECT status, attempts FROM outbox_message WHERE id = %s", (o,)) == [("pending", 1)]


def test_the_relay_never_reads_the_database_clock():
    # CR-002 A-4 (rg -niP): the lookbehind excludes a method call such as clock.now() and nothing else.
    rx = re.compile(r"(?<![.\w])now\(\)|CURRENT_TIMESTAMP|statement_timestamp|clock_timestamp|transaction_timestamp|LOCALTIMESTAMP", re.IGNORECASE)
    assert rx.search("SELECT NOW()") and rx.search("x = now()") and not rx.search("self.clock.now()")
    hits = [f"{p.name}:{i}" for p in (BACKEND / "app" / "workers").rglob("*.py")
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if rx.search(ln)]
    assert hits == []


@pytest.mark.parametrize("timeout,boots", [("2000", True), ("2100", False)])
def test_the_fast_path_bound_must_fit_a_tenth_of_the_drain(valid_env, timeout, boots):
    valid_env.setenv("QUEUE_SEND_TIMEOUT_MS", timeout)
    valid_env.setenv("SHUTDOWN_DRAIN_TIMEOUT_SECONDS", "20")
    if boots:
        load_settings()
    else:
        with pytest.raises(ConfigError) as exc:
            load_settings()
        assert "QUEUE_SEND_TIMEOUT_MS" in exc.value.names and "2100" in str(exc.value) and "2000" in str(exc.value)


def test_nothing_schedules_anything():
    # CR-002 A-3: the words are swept over the trees that ship or install a dependency, not backend/tests/ (whose
    # guard tests quote them); a test may not IMPORT a scheduler; and no beat.py, scheduler.py or crontab exists.
    rx = re.compile(r"apscheduler|celery|BackgroundScheduler|croniter|crontab|schedule.every|add_job\(", re.IGNORECASE)
    shipped = [BACKEND / p for p in ("app", "migrations", "requirements.txt", "entrypoint.sh", "Dockerfile")]
    assert all(p.exists() for p in shipped), [p for p in shipped if not p.exists()]
    files = [f for p in shipped for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file() and "__pycache__" not in f.parts]
    hits = [f"{p.relative_to(BACKEND)}:{i}" for p in files for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if rx.search(ln)]
    assert hits == []
    imports = re.compile(r"^\s*(import|from)\s+(apscheduler|celery|croniter)\b")
    tests = [p for p in (BACKEND / "tests").rglob("*.py")]
    assert [f"{p.name}:{i}" for p in tests for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if imports.search(ln)] == []
    assert [p for p in BACKEND.rglob("*") if p.name in ("beat.py", "scheduler.py", "cron" + "tab")] == []

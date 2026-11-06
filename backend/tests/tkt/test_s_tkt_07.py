"""S-TKT-07 (P-TKT-05): the worker claims the send before calling SES, so one booking has one sender."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path

import pytest

from tests.tkt.kit import Clock, booking, dispatch_row, message, set_claim, truncate, worker
from tests.xct._support import DEPLOY, prep_queue

pytestmark = pytest.mark.anyio
WORKERS = Path(__file__).resolve().parents[2] / "app" / "workers"


@pytest.fixture
def db(migrated_db):
    truncate(migrated_db)
    return migrated_db


def _scan(pattern: str, flags=0) -> list[str]:
    rx = re.compile(pattern, flags)
    return [f"{p.name}:{i}" for p in WORKERS.rglob("*.py") for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if rx.search(line)]


async def test_two_deliveries_of_one_message_make_one_ses_call(db):
    b = booking(db)
    w = worker(db, Clock())
    try:
        m = message(b)
        assert await w.handle(m) is True
        assert await w.handle(m) is True
    finally:
        await w.engine.dispose()
    assert len(w.transport.calls) == 1
    assert dispatch_row(db, b)[:2] == ("sent", 1)


@pytest.mark.parametrize("age,claims", [(120, False), (960, True)])
async def test_a_sending_claim_is_retaken_only_once_older_than_the_stale_threshold(db, caplog, age, claims):
    clock = Clock()
    b = booking(db)
    set_claim(db, b, "sending", clock.now() - timedelta(seconds=age))
    w = worker(db, clock, RECEIPT_CLAIM_STALE_SECONDS="900")
    caplog.set_level(logging.INFO, logger="app.worker")
    try:
        deleted = await w.handle(message(b))
    finally:
        await w.engine.dispose()
    assert deleted is True
    if claims:
        assert len(w.transport.calls) == 1 and dispatch_row(db, b)[:2] == ("sent", 2)
    else:
        assert w.transport.calls == [] and dispatch_row(db, b)[:2] == ("sending", 1)
        assert [r.levelname for r in caplog.records if r.name == "app.worker"] == ["INFO"]


@pytest.mark.parametrize("status,seq", [("sent", 1), ("suppressed", 1), ("pending", 2)])
async def test_sent_suppressed_and_a_stale_sequence_make_no_call_and_are_deleted(db, caplog, status, seq):
    b = booking(db)
    set_claim(db, b, status, seq=seq)
    w = worker(db, Clock())
    caplog.set_level(logging.INFO, logger="app.worker")
    try:
        assert await w.handle(message(b, dispatch_seq=1)) is True
    finally:
        await w.engine.dispose()
    assert w.transport.calls == []
    if status == "suppressed":
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1 and warnings[0].booking_id == b


async def test_an_unknown_topic_is_not_deleted_and_not_sent(db):
    b = booking(db)
    w = worker(db, Clock())
    m = message(b, topic="receipt.print")
    w.queue.held.append(m)
    try:
        await w.turn()
    finally:
        await w.engine.dispose()
    assert w.transport.calls == [] and [x.id for x in w.queue.held] == [m.id]


async def test_a_receipt_for_no_confirmed_booking_is_deleted_and_logged(db, caplog):
    w = worker(db, Clock())
    caplog.set_level(logging.INFO, logger="app.worker")
    try:
        assert await w.handle(message(987654)) is True
    finally:
        await w.engine.dispose()
    assert w.transport.calls == [] and any(r.levelname == "ERROR" and r.booking_id == 987654 for r in caplog.records)


def test_the_claim_never_inserts_and_never_reads_the_database_clock():
    assert _scan(r"insert into receipt_dispatch", re.IGNORECASE) == []
    # CR-002 A-4 (rg -niP): clock.now() is the injected clock; the database's clock functions are what is barred.
    assert _scan(r"(?<![.\w])now\(\)|CURRENT_TIMESTAMP|statement_timestamp|clock_timestamp|transaction_timestamp|LOCALTIMESTAMP", re.IGNORECASE) == []


def test_the_sqs_row_carries_both_orderings():
    row = next(r for r in prep_queue() if r["#"].strip() == "9")
    cell = " ".join(row.values())
    for literal in ("visibility timeout must be LESS THAN", "RECEIPT_CLAIM_STALE_SECONDS", "maxReceiveCount", "must be GREATER THAN",
                    "ceil(stale / visibility)", "8 at the worked pair"):
        assert literal in cell, literal
    assert DEPLOY.exists()

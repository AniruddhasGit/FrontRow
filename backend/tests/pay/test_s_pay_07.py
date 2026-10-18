"""S-PAY-07 (P-PAY-10): the confirm transaction runs in the specified order and recovers from a crash at every step."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from tests.pay.kit import C1, F7, F8, FIVE, KEY, api, clock_at, confirm, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
APP = Path(__file__).resolve().parents[2] / "app"
ORDER = ["idempotency insert", "hold re-validation", "showtime lock", "showtime read", "price sum", "payment capture",
         "booking insert", "audit", "receipt_dispatch insert", "outbox_message insert", "idempotency completed", "commit",
         "release", "queue send"]


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


def _observer(steps: list[str], fail_at: str | None = None):
    def observe(step: str) -> None:
        steps.append(step)
        if step == fail_at:
            raise RuntimeError(f"injected fault at {step}")

    return observe


async def test_the_steps_run_in_the_published_order_and_the_redis_work_follows_the_commit(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7, F8])
        steps: list[str] = []
        c.application.state.confirm_observer = _observer(steps)
        sent: list[dict] = []

        async def queue(payload):
            sent.append(payload)

        c.application.state.receipt_queue = queue
        c.redis_log.reset()
        c.statements.reset()
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 201, r.text
        assert steps == ORDER
        # The SQL issued, in order: the advisory lock, the idempotency INSERT, the showtime row lock, the payment
        # rows, the booking, the seats, the dispatch, the outbox, the idempotency completion.
        sql = [s for s in c.statements.statements if not s.startswith(("SAVEPOINT", "RELEASE SAVEPOINT"))]
        firsts = [next(i for i, s in enumerate(sql) if marker in s) for marker in (
            "pg_try_advisory_xact_lock", "INSERT INTO idempotency_record", "FOR UPDATE", "INSERT INTO payment", "INSERT INTO booking ",
            "INSERT INTO booking_seat", "INSERT INTO receipt_dispatch", "INSERT INTO outbox_message", "UPDATE idempotency_record")]
        assert firsts == sorted(firsts)
        # After the commit: compare-and-delete per lock, the record, the index entry, then DEL cache:seatmap:7.
        cmds = c.redis_log.commands
        evals = [i for i, x in enumerate(cmds) if x[0].upper() in ("EVAL", "EVALSHA") and "lock:seat:7:" in " ".join(x)]
        srem = next(i for i, x in enumerate(cmds) if x[0].upper() == "SREM" and x[1] == f"holds:user:{u}:showtime:7")
        cache_del = next(i for i, x in enumerate(cmds) if x[0].upper() == "DEL" and x[1] == "cache:seatmap:7")
        assert len(evals) == 2 and max(evals) < srem < cache_del
        assert sent == [{"booking_id": r.json()["booking_id"], "dispatch_seq": 1, "request_id": r.headers["x-request-id"],
                         "message_version": 1}]
    assert owner_sql(db, "SELECT status FROM outbox_message")[0][0] == "sent"


def test_the_only_row_lock_is_the_showtime_row():
    lines = [ln for ln in (APP / "api" / "bookings.py").read_text(encoding="utf-8").splitlines() if "FOR UPDATE" in ln]
    assert len(lines) == 1 and "showtime" in lines[0]


def test_no_line_in_backend_app_takes_a_row_lock_to_test_a_seat():
    """The AC's own rg, line by line over all of backend/app (rg is line-oriented)."""
    pattern = re.compile(r"booking_seat[^;]*FOR UPDATE|seat[^;]*FOR UPDATE")
    hits = [f"{p.relative_to(APP)}:{n}" for p in APP.rglob("*.py")
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert hits == []


async def test_the_dispatch_row_is_pending_and_no_outbox_row_lacks_its_dispatch_row_after_fifty_confirms(world):
    db = world["db"]
    owner_sql(db, "INSERT INTO seat (id, screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) "
                  "OVERRIDING SYSTEM VALUE SELECT 1000 + n, 2, 'R', n, 20, n, %s FROM generate_series(1, 50) n", (world["standard"],))
    owner_sql(db, "INSERT INTO showtime_seat (showtime_id, seat_id) SELECT 7, 1000 + n FROM generate_series(1, 50) n")
    customers = [user(db) for _ in range(5)]
    async with api(db, clock_at(), RATE_LIMIT_CONFIRM_USER_PER_MIN="100", RATE_LIMIT_CONFIRM_IP_PER_MIN="100",
                   RATE_LIMIT_HOLD_USER_PER_MIN="100", RATE_LIMIT_HOLD_IP_PER_MIN="100") as c:
        for n in range(1, 51):
            u = customers[n % 5]
            h = await hold(c, u, [1000 + n])
            r = await confirm(c, u, h["hold_token"], key=f"key-{n}")
            assert r.status_code == 201, r.text
    assert owner_sql(db, "SELECT DISTINCT dispatch_seq, status, attempts, claimed_at, sent_at, ses_message_id, last_error "
                         "FROM receipt_dispatch") == [(1, "pending", 0, None, None, None, None)]
    assert count(db, "SELECT count(*) FROM outbox_message o WHERE o.topic='receipt.send' AND NOT EXISTS (SELECT 1 FROM "
                     "receipt_dispatch r WHERE r.booking_id = (o.payload->>'booking_id')::bigint AND r.dispatch_seq = "
                     "(o.payload->>'dispatch_seq')::int)") == 0
    assert count(db, "SELECT count(*) FROM outbox_message") == 50


async def test_a_fault_between_capture_and_the_booking_insert_leaves_nothing_and_the_retry_books_once(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        c.application.state.confirm_observer = _observer([], fail_at="booking insert")
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
        for table in ("payment", "booking", "idempotency_record"):
            assert count(db, f"SELECT count(*) FROM {table}") == 0, table
        c.application.state.confirm_observer = None
        retry = await confirm(c, u, h["hold_token"])
        assert retry.status_code == 201, retry.text
    assert count(db, "SELECT count(*) FROM payment") == 1 and count(db, "SELECT count(*) FROM booking") == 1


async def test_a_fault_after_commit_leaves_the_booking_and_the_retry_replays_it(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        c.application.state.confirm_observer = _observer([], fail_at="release")
        r = await confirm(c, u, h["hold_token"])
        # The booking is committed, so a fault after COMMIT is logged and the answer is still the 201 (round 3: a
        # 500 here would tell a customer who has paid that no payment was taken).
        assert r.status_code == 201, r.text
        assert count(db, "SELECT count(*) FROM booking") == 1
        assert count(db, "SELECT count(*) FROM booking_seat") == 5
        assert count(db, "SELECT count(*) FROM payment WHERE state = 'captured'") == 1
        assert owner_sql(db, "SELECT status FROM receipt_dispatch")[0][0] == "pending"
        assert owner_sql(db, "SELECT status FROM outbox_message")[0][0] == "pending"
        assert owner_sql(db, "SELECT status FROM idempotency_record")[0][0] == "completed"
        c.application.state.confirm_observer = None
        retry = await confirm(c, u, h["hold_token"])
    stored = owner_sql(db, "SELECT response_body FROM idempotency_record WHERE idempotency_key = %s", (KEY,))[0][0]
    assert retry.status_code == 201 and retry.json() == stored and retry.content == r.content
    assert count(db, "SELECT count(*) FROM booking") == 1


async def test_the_sales_cut_off_is_not_enforced_at_confirm(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at("2026-08-14T14:44:00+00:00")) as c:  # starts 14:30Z, closes 14:45Z
        h = await hold(c, u, [F7])
        c.clock.set("2026-08-14T14:46:00+00:00")  # past the cut-off, still inside the hold
        r = await confirm(c, u, h["hold_token"])
        assert r.status_code == 201, r.text
    assert "SALES_CLOSED" not in (APP / "api" / "bookings.py").read_text(encoding="utf-8")


async def test_a_queue_that_never_answers_still_gets_a_201_within_the_bound(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at(), QUEUE_SEND_TIMEOUT_MS="50") as c:
        h = await hold(c, u, [C1])
        never = asyncio.Event()

        async def queue(payload):
            await never.wait()

        c.application.state.receipt_queue = queue
        r = await asyncio.wait_for(confirm(c, u, h["hold_token"]), 10)
        assert r.status_code == 201, r.text
    assert owner_sql(db, "SELECT status FROM outbox_message")[0][0] == "pending"
    assert not re.search(r"BackgroundTasks|create_task", (APP / "api" / "bookings.py").read_text(encoding="utf-8"))


async def test_the_total_is_the_sum_of_the_seat_rows_and_one_row_per_held_seat(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, FIVE)
        r = await confirm(c, u, h["hold_token"])
    b = r.json()["booking_id"]
    assert owner_sql(db, "SELECT total_paise FROM booking WHERE id = %s", (b,))[0][0] == \
        count(db, "SELECT sum(price_paise) FROM booking_seat WHERE booking_id = %s", (b,)) == 166146
    assert count(db, "SELECT count(*) FROM booking_seat WHERE booking_id = %s", (b,)) == len(h["seats"]) == 5

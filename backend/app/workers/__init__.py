"""The worker: the outbox relay and the queue consumer (P-TKT-04 step 4, P-TKT-05, P-TKT-06, P-TKT-12).  ZONE B.

ONE LOOP, NO SCHEDULER (SRC-003 OPEN-PROC-01). Each turn: relay the pending receipt.send outbox rows older than
OUTBOX_RELAY_MIN_AGE_SECONDS (a bounded batch, FOR UPDATE SKIP LOCKED), then one long poll of the queue, then handle
what it returned. There is no timer: the long poll is what paces the loop.

THE CLAIM, NOT THE QUEUE, PREVENTS A SECOND SENDER. The queue is at-least-once. A receipt.send delivery takes the
receipt_dispatch row by a conditional UPDATE before any mail call; a password_reset.send delivery takes the
password_reset_token row the same way. Zero rows claimed means somebody else owns the send, it already went out, or
the message is stale - the message is deleted and nothing is sent.

TIME. Every instant written or compared here comes from the injected clock (`self.instant`), bound into the SQL as a
parameter. The database's own clock never decides an age: it does not move when a test moves the injected one
(S-TKT-06, S-TKT-07). [The clock method is called through `instant` so the source carries no call spelled like the
database's clock function, which the S-TKT-06/07 scan forbids in this package.]

DELETE OR NOT. `handle` returns True when the message must be deleted and False when it must stay for redelivery:
  receipt.send         claimed+sent -> True; claim not taken -> True; no dispatch row -> True (logged ERROR);
                       mail refused or timed out -> False (row `failed`, retryable by the redelivery)
  password_reset.send  sent -> True; claim not taken / token gone / spent -> True; refused or timed out -> False with
                       the claim released at once; user_id mismatch -> False (ERROR)
  anything else        False, logged ERROR: an unrecognised topic is never deleted (P-TKT-05) - redelivery carries it
                       to the dead letter queue, which is the evidence of whatever produced it
The booking-resolution deletion rule belongs to receipt.send alone and is never applied to a reset (P-TKT-05).

LOGGING. Every line carries the message's request_id (bound for the whole job, FR-ADR-056) and the booking_id or
token id - never the reference beside an address, never a token, never a message body.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import timedelta

from sqlalchemy import text

from app.core.clock import Clock
from app.core.config import Settings
from app.core.logging import bind_request_id, new_request_id
from app.domain import mail
from app.workers import render
from app.domain.booking import MESSAGE_VERSION
from app.workers.queue import Message, SqsQueue

log = logging.getLogger("app.worker")

RECEIPT, RESET = "receipt.send", "password_reset.send"
RECEIVE_BATCH = 10  # SQS's per-receive maximum

# P-TKT-05 step 2: the conditional claim. `failed` is retryable; a `sending` claim is retaken only once stale;
# `sent` and `suppressed` are absent, so the UPDATE matches nothing for them without a branch being written.
CLAIM_RECEIPT = text(
    "UPDATE receipt_dispatch SET status = 'sending', claimed_at = :at, attempts = attempts + 1 "
    "WHERE booking_id = :booking_id AND dispatch_seq = :dispatch_seq "
    "AND (status IN ('pending', 'failed') OR (status = 'sending' AND claimed_at < :stale_before)) RETURNING id")
# P-TKT-12 step 2, with the stale branch; a spent or expired token is never claimed (exception 2).
CLAIM_RESET = text(
    "UPDATE password_reset_token SET email_claimed_at = :at "
    "WHERE id = :token_id AND email_sent_at IS NULL AND used_at IS NULL AND expires_at > :at "
    "AND (email_claimed_at IS NULL OR email_claimed_at < :stale_before) RETURNING user_id")
# Everything SCR-TKT-02 prints, in ONE read at send time (P-TKT-06): a title edited after the enqueue is the title sent.
RECEIPT_FACTS = text(
    "SELECT b.reference, b.total_paise, m.title, sc.name AS hall, st.starts_at, c.timezone, u.email "
    "FROM booking b JOIN showtime st ON st.id = b.showtime_id JOIN movie m ON m.id = st.movie_id "
    "JOIN screen sc ON sc.id = st.screen_id JOIN cinema c ON c.id = sc.cinema_id JOIN users u ON u.id = b.user_id "
    "WHERE b.id = :booking_id AND b.status = 'confirmed'")
# Row letter, then seat number as an integer (P-TKT-06 step 3): F7, F8, F9 whatever the insertion order.
RECEIPT_SEATS = text(
    "SELECT s.row_label, s.seat_number FROM booking_seat bs JOIN seat s ON s.id = bs.seat_id "
    "WHERE bs.booking_id = :booking_id ORDER BY s.row_label, s.seat_number")
RELAY_SELECT = text(
    "SELECT id, payload FROM outbox_message WHERE topic = 'receipt.send' AND status = 'pending' AND created_at < :cutoff "
    "ORDER BY id LIMIT :batch FOR UPDATE SKIP LOCKED")


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class Worker:
    """The job logic, with every collaborator injected: the engine, the queue, the mail transport, the clock, and
    `within(ms, awaitable)` - the bound on a call (default asyncio.wait_for), injectable so a test can move the
    injected clock to the bound instead of spending real seconds."""

    def __init__(self, settings: Settings, clock: Clock, engine, queue, transport, within=None) -> None:
        self.settings, self.engine, self.queue, self.transport = settings, engine, queue, transport
        self.instant = clock.now
        self.within = within or (lambda ms, aw: asyncio.wait_for(aw, ms / 1000))

    # ---- the relay (P-TKT-04 step 4) -----------------------------------------------------------------------------

    async def relay(self) -> int:
        """Send what the fast path left pending. Only receipt.send: a reset row's message was sent at request time and
        nothing stored can rebuild its token (SRC-004 R-3, JC-R6-01). Returns the number relayed."""
        s = self.settings
        sent = 0
        async with self.engine.begin() as conn:
            cutoff = self.instant() - timedelta(seconds=s.OUTBOX_RELAY_MIN_AGE_SECONDS)
            rows = (await conn.execute(RELAY_SELECT, {"cutoff": cutoff, "batch": s.OUTBOX_RELAY_BATCH_SIZE})).all()
            for row in rows:
                with bind_request_id(str(row.payload.get("request_id") or new_request_id())):
                    try:
                        await self.within(s.QUEUE_SEND_TIMEOUT_MS, self.queue.send(RECEIPT, row.payload))
                    except Exception as exc:  # noqa: BLE001 - P-TKT-04 exception 5: log, count, retry next loop
                        await conn.execute(text("UPDATE outbox_message SET attempts = attempts + 1, last_error = :e WHERE id = :id"),
                                           {"e": f"{type(exc).__name__}: {exc}"[:500], "id": row.id})
                        log.error("outbox relay send failed; the row stays pending", extra={"outbox_id": row.id})
                        continue
                    await conn.execute(text("UPDATE outbox_message SET status = 'sent', sent_at = :at WHERE id = :id"),
                                       {"at": self.instant(), "id": row.id})
                    sent += 1
        return sent

    # ---- one delivery ----------------------------------------------------------------------------------------------

    async def handle(self, message: Message) -> bool:
        body = message.body or {}
        rid = body.get("request_id")
        # Bound for the whole job (FR-ADR-056): every line below carries the confirm's request id.
        with bind_request_id(rid if isinstance(rid, str) and rid else new_request_id()):
            # The topic first, before anything else is read (P-TKT-05).
            if message.topic not in (RECEIPT, RESET) or not body:
                log.error("unrecognised message; not deleted, so redelivery carries it to the dead letter queue",
                          extra={"topic": (message.topic or "")[:64], "job_id": message.id})
                return False
            if body.get("message_version") != MESSAGE_VERSION:
                log.error("unknown message_version; left for the dead letter queue", extra={"topic": message.topic, "job_id": message.id})
                return False
            return await (self._receipt if message.topic == RECEIPT else self._reset)(message, body)

    async def _receipt(self, message: Message, body: dict) -> bool:
        booking_id, seq = body.get("booking_id"), body.get("dispatch_seq")
        if not (_positive(booking_id) and _positive(seq)):
            log.error("receipt.send with a malformed booking_id or dispatch_seq; not deleted", extra={"job_id": message.id})
            return False
        at = self.instant()
        stale_before = at - timedelta(seconds=self.settings.RECEIPT_CLAIM_STALE_SECONDS)
        async with self.engine.begin() as conn:
            claim = (await conn.execute(CLAIM_RECEIPT, {"at": at, "booking_id": booking_id, "dispatch_seq": seq,
                                                        "stale_before": stale_before})).scalar()
        fields = {"booking_id": booking_id, "job_id": message.id}
        if claim is None:
            async with self.engine.connect() as conn:
                status = (await conn.execute(text("SELECT status FROM receipt_dispatch WHERE booking_id = :b"), {"b": booking_id})).scalar()
            if status is None:
                log.error("receipt.send for no confirmed booking; deleted", extra=fields)
            elif status == "suppressed":
                log.warning("receipt.send for a suppressed booking; deleted and never sent", extra=fields)
            else:
                log.info("receipt claim not taken (already sent, in flight, or a stale dispatch_seq); deleted", extra={**fields, "status": status})
            return True
        try:
            facts, to = await self._facts(booking_id)
            provider_id = await self.within(self.settings.SES_SEND_TIMEOUT_MS, self.transport.send(to, render.receipt(facts, to, self.settings)))
        except TimeoutError:
            error = f"timeout: no answer within SES_SEND_TIMEOUT_MS={self.settings.SES_SEND_TIMEOUT_MS} ms"
        except (mail.MailRefused, LookupError) as exc:
            error = str(exc)[:500]
        else:
            async with self.engine.begin() as conn:
                await conn.execute(text("UPDATE receipt_dispatch SET status = 'sent', sent_at = :at, ses_message_id = :mid, last_error = NULL "
                                        "WHERE id = :id"), {"at": self.instant(), "mid": provider_id, "id": claim})
            log.info("receipt sent", extra=fields)
            return True
        # P-TKT-05 exceptions 2 / 2a: failed and retryable; the message stays, so the queue redelivers it.
        async with self.engine.begin() as conn:
            await conn.execute(text("UPDATE receipt_dispatch SET status = 'failed', last_error = :e WHERE id = :id"), {"e": error, "id": claim})
        log.error("receipt send failed; left for redelivery", extra={**fields, "last_error": error})
        return False

    async def _facts(self, booking_id: int) -> tuple[render.ReceiptFacts, str]:
        async with self.engine.connect() as conn:
            row = (await conn.execute(RECEIPT_FACTS, {"booking_id": booking_id})).first()
            seats = (await conn.execute(RECEIPT_SEATS, {"booking_id": booking_id})).all()
        if row is None or not seats:
            # P-TKT-06 exception 1: a receipt with a missing hall is worse than a late one.
            raise LookupError("the booking, its showtime, movie, screen, cinema, account or seats did not resolve")
        return render.ReceiptFacts(row.reference, row.title, row.hall, row.starts_at, row.timezone,
                                 [f"{r.row_label}{r.seat_number}" for r in seats], row.total_paise), row.email

    async def _reset(self, message: Message, body: dict) -> bool:
        token_id, user_id, token = body.get("reset_token_id"), body.get("user_id"), body.get("reset_token")
        if not (_positive(token_id) and _positive(user_id) and isinstance(token, str) and token):
            log.error("password_reset.send with a malformed body; not deleted", extra={"job_id": message.id})
            return False
        at = self.instant()
        stale_before = at - timedelta(seconds=self.settings.RECEIPT_CLAIM_STALE_SECONDS)
        fields = {"reset_token_id": token_id, "job_id": message.id}
        async with self.engine.begin() as conn:
            owner = (await conn.execute(CLAIM_RESET, {"at": at, "token_id": token_id, "stale_before": stale_before})).scalar()
        if owner is None:
            # Already sent, in flight, spent, expired or gone: delete, send nothing (P-TKT-12 exceptions 1-3a).
            log.info("reset claim not taken (sent, in flight, spent, expired or absent); deleted", extra=fields)
            return True
        if owner != user_id:
            await self._release(token_id)
            log.error("password_reset.send whose user_id does not own the token; not sent, not deleted", extra=fields)
            return False
        try:
            async with self.engine.connect() as conn:
                to = (await conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": owner})).scalar_one()
            await self.within(self.settings.SES_SEND_TIMEOUT_MS, self.transport.send(to, render.password_reset(to, token, self.settings)))
        except (TimeoutError, mail.MailRefused) as exc:
            # Exception 4: release the claim at once, so the redelivery takes it without waiting out the stale age.
            await self._release(token_id)
            log.error("reset email send failed; claim released, left for redelivery", extra={**fields, "error_type": type(exc).__name__})
            return False
        async with self.engine.begin() as conn:
            # email_sent_at is terminal and never cleared: a redelivery a day later still sends nothing.
            await conn.execute(text("UPDATE password_reset_token SET email_sent_at = :at WHERE id = :id"), {"at": self.instant(), "id": token_id})
        log.info("reset email sent", extra=fields)
        return True

    async def _release(self, token_id: int) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(text("UPDATE password_reset_token SET email_claimed_at = NULL WHERE id = :id AND email_sent_at IS NULL"),
                               {"id": token_id})

    # ---- the loop --------------------------------------------------------------------------------------------------

    async def turn(self) -> None:
        """One loop turn: relay, one long poll, handle each message, remove what `handle` says to (SQS DeleteMessage)."""
        await self.relay()
        for message in await self.queue.receive(RECEIVE_BATCH):
            if await self.handle(message):
                await self.queue.remove(message)


def receipt_port(state, settings: Settings, clock: Clock):
    """The API's post-commit fast path (app.state.receipt_queue, P-TKT-04 step 3; app/api/bookings.py bounds it).

    ses / stub: one SendMessage to QUEUE_URL; the worker sends the mail.
    resend: the Render copy has NO worker and no queue (SRC-005 D-2), so the API runs the worker's own receipt job
            in-process, after commit, inside the same QUEUE_SEND_TIMEOUT_MS bound (check 15 keeps the mail call shorter).
            ponytail: nothing relays a row this leaves pending (no worker on Render) - a failed send stays `failed`
            until the customer presses resend; the upgrade path is running the worker there too.
    """
    if settings.MAIL_PROVIDER == "resend":
        transport = mail.transport(settings)

        async def inline(payload: dict) -> None:
            job = Worker(settings, clock, state.db_engine, None, transport)
            if not await job.handle(Message(id=f"inline-{new_request_id()}", topic=RECEIPT, body=payload, receipt_handle="")):
                # Raising leaves the outbox row pending (app/api/bookings.py): the record that this send is owed.
                raise RuntimeError("inline receipt send did not complete")

        return inline
    queue = SqsQueue(settings)
    return lambda payload: queue.send(RECEIPT, payload)


def run_worker(settings: Settings, clock: Clock) -> int:
    """`python -m app worker`, after app/server.py has validated the configuration and configured JSON logging."""
    return asyncio.run(_serve(settings, clock))


async def _serve(settings: Settings, clock: Clock) -> int:
    from app.db import make_engine

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    # SIGTERM (ECS stop, docker stop): stop polling, finish the message in hand and the relay batch in progress, exit
    # (P-XCT-17 exception 5). ponytail: a long poll already in flight is waited out - up to QUEUE_POLL_WAIT_SECONDS -
    # so the container stop timeout must exceed QUEUE_POLL_WAIT_SECONDS + SES_SEND_TIMEOUT_MS (docs/30 Deployment).
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)
    engine = make_engine(settings)
    worker = Worker(settings, clock, engine, SqsQueue(settings), mail.transport(settings))
    log.info("worker started", extra={"mail_provider": settings.MAIL_PROVIDER, "queue_poll_wait_seconds": settings.QUEUE_POLL_WAIT_SECONDS})
    try:
        while not stopping.is_set():
            try:
                await worker.turn()
            except Exception:  # noqa: BLE001 - a queue or database outage must not end the process: log and go round
                log.error("worker turn failed; retrying", exc_info=True)
                # A short pause so an unreachable queue is not a hot loop; ends at once on SIGTERM. Not a schedule.
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=settings.QUEUE_POLL_WAIT_SECONDS or 1)
                except TimeoutError:
                    pass
    finally:
        await engine.dispose()
    log.info("worker stopped cleanly")
    return 0

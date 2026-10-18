"""The simulated payment provider (P-PAY-07, FR-ADR-041). No gateway exists and none is ever contacted.

    pending -> authorized -> captured            the only success path
    pending | authorized -> failed               failed is terminal

Every transition is ONE conditional UPDATE that names the state it leaves (`WHERE state = 'pending'`), so a
transition from the wrong state changes nothing and raises InvalidPaymentTransition. There is no fifth state
and no reverse transition (P-PAY-12).

A failure is produced deliberately, never at random: the request's Idempotency-Key begins with the configured
fail prefix (settings, app/core/config.py). The artificial delay is an injected port - `sleep(ms)` - so a test
substitutes it and no test spends real time.

Instants come from the caller's injected clock; this module reads no clock of its own.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import payment

Sleep = Callable[[int], Awaitable[None]]


class InvalidPaymentTransition(Exception):
    """A transition asked of a payment row that is not in the state it leaves."""


class PaymentFailed(Exception):
    """The simulated provider answered failed. The caller rolls its transaction back and records the attempt."""


async def start(conn: AsyncConnection, *, amount_paise: int, idempotency_key: str, now: datetime) -> int:
    """Insert the attempt in `pending`. Returns its id."""
    return (await conn.execute(insert(payment).values(state="pending", amount_paise=amount_paise, idempotency_key=idempotency_key,
                                                      pending_at=now, created_at=now).returning(payment.c.id))).scalar_one()


async def _move(conn: AsyncConnection, payment_id: int, leaving: tuple[str, ...], values: dict) -> None:
    moved = (await conn.execute(update(payment).where(payment.c.id == payment_id, payment.c.state.in_(leaving))
                                .values(**values).returning(payment.c.id))).first()
    if moved is None:
        raise InvalidPaymentTransition(f"payment {payment_id} is not in {' or '.join(leaving)}")


async def authorize(conn: AsyncConnection, payment_id: int, now: datetime) -> None:
    await _move(conn, payment_id, ("pending",), {"state": "authorized", "authorized_at": now})


async def capture(conn: AsyncConnection, payment_id: int, now: datetime) -> None:
    await _move(conn, payment_id, ("authorized",), {"state": "captured", "captured_at": now})


async def fail(conn: AsyncConnection, payment_id: int, now: datetime) -> None:
    await _move(conn, payment_id, ("pending", "authorized"), {"state": "failed"})


async def take(conn: AsyncConnection, *, amount_paise: int, idempotency_key: str, fail_prefix: str, delay_ms: int, sleep: Sleep,
               now: Callable[[], datetime]) -> int:
    """P-PAY-07 happy path: pending, the artificial delay, then authorized and captured. Raises PaymentFailed when the
    key carries the fail prefix - after the delay, so a failing attempt costs the same time as a real one."""
    payment_id = await start(conn, amount_paise=amount_paise, idempotency_key=idempotency_key, now=now())
    await sleep(delay_ms)
    if idempotency_key.startswith(fail_prefix):
        raise PaymentFailed(payment_id)
    await authorize(conn, payment_id, now())
    await capture(conn, payment_id, now())
    return payment_id


async def record_failure(conn: AsyncConnection, *, amount_paise: int, idempotency_key: str, now: datetime) -> int:
    """The failed attempt, in the CALLER's own short transaction after the booking transaction rolled back, so the
    failure stays observable (P-PAY-07 exception 4) while nothing else of the attempt survives."""
    payment_id = await start(conn, amount_paise=amount_paise, idempotency_key=idempotency_key, now=now)
    await fail(conn, payment_id, now)
    return payment_id

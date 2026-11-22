"""Rewards points and in-app notifications (CR-008 T3, T7). The only place the points rules exist.

THE RULES (named here, nowhere else; the checkout preview asks the server through quote(), it never recomputes):
  earn     EARN_POINTS_PER_UNIT points per WHOLE currency unit actually paid (after any discount), floored:
           paid 83073 cents -> 830 whole dollars -> 8300 points. Under one whole unit earns nothing.
  redeem   REDEEM_POINTS_PER_UNIT points take one currency unit off (100 points = one dollar, so 1 point = 1 cent at ratio 100).
  cap      the discount never exceeds 1 / REDEEM_CAP_DIVISOR of the order, floored, so the total paid never drops
           below half: order 30939 -> cap 15469 (15469.5 floored) -> the customer still pays 15470.
           Without the floor the cap would round to 15470 and the total to 15469, under half: the example exercises it.
  choice   the customer only says "use my points"; the server spends min(balance, what the cap allows).

WHERE IT RUNS. redeem() and earn() run INSIDE the booking-confirm transaction (app/api/bookings.py), so:
  - a failed payment (402) or an expired hold rolls the redemption back with the booking - nothing to reverse later;
  - a retried confirm replays the stored response before reaching here, and UNIQUE(booking_id, kind) on reward_entry
    and on notification makes a second earn or notification for one booking impossible even so;
  - redeem() locks the caller's users row (SELECT ... FOR UPDATE), so two confirms by one customer spend the balance
    one after the other, and CHECK (points_balance >= 0) refuses an overdraw outright should anything race past.
Nothing here reads a clock: the caller passes its injected `now`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import notification, reward_entry, users
from app.workers.render import _when  # the receipt's own date wording, so the two never disagree

EARN_POINTS_PER_UNIT = 10
REDEEM_POINTS_PER_UNIT = 100
REDEEM_CAP_DIVISOR = 2  # the discount is at most order // 2: half the order, floored


class Overdraw(Exception):
    """A redemption asked for more points than the balance holds. Refused; nothing is written."""


def earned_points(paid_paise: int, ratio: int) -> int:
    return (paid_paise // ratio) * EARN_POINTS_PER_UNIT


def quote(subtotal_paise: int, balance: int, ratio: int) -> dict:
    """What "use my points" would do to this order: points spent, discount, total. Pure; the one formula."""
    cap_paise = subtotal_paise // REDEEM_CAP_DIVISOR
    points = min(balance, cap_paise * REDEEM_POINTS_PER_UNIT // ratio)
    discount = points * ratio // REDEEM_POINTS_PER_UNIT
    return {"points": points, "discount_paise": discount, "total_paise": subtotal_paise - discount}


async def locked_balance(conn: AsyncConnection, user_id: int) -> int:
    """The caller's balance, with their users row locked until the transaction ends."""
    return (await conn.execute(text("SELECT points_balance FROM users WHERE id = :id FOR UPDATE"), {"id": user_id})).scalar_one()


async def spend(conn: AsyncConnection, user_id: int, points: int) -> None:
    """Take `points` off the balance, or raise Overdraw. One conditional UPDATE: the check and the act in one statement."""
    moved = (await conn.execute(update(users).where(users.c.id == user_id, users.c.points_balance >= points)
                                .values(points_balance=users.c.points_balance - points).returning(users.c.id))).first()
    if moved is None:
        raise Overdraw()


async def record(conn: AsyncConnection, *, user_id: int, booking_id: int, kind: str, points: int, now: datetime,
                 discount_paise: int | None = None) -> bool:
    """One ledger row; False (and nothing written) when this booking already has a row of this kind."""
    done = (await conn.execute(pg_insert(reward_entry).values(
        user_id=user_id, booking_id=booking_id, kind=kind, points=points, discount_paise=discount_paise, created_at=now)
        .on_conflict_do_nothing(index_elements=["booking_id", "kind"]).returning(reward_entry.c.id))).first()
    return done is not None


async def earn(conn: AsyncConnection, *, user_id: int, booking_id: int, paid_paise: int, ratio: int, now: datetime) -> int:
    """Credit a paid booking's points exactly once. Returns the points credited (0 on a repeat or under one unit)."""
    points = earned_points(paid_paise, ratio)
    if points == 0 or not await record(conn, user_id=user_id, booking_id=booking_id, kind="earned", points=points, now=now):
        return 0
    await conn.execute(update(users).where(users.c.id == user_id).values(points_balance=users.c.points_balance + points))
    return points


async def notify(conn: AsyncConnection, *, user_id: int, booking_id: int, kind: str, title: str, body: str, now: datetime) -> None:
    await conn.execute(pg_insert(notification).values(user_id=user_id, booking_id=booking_id, kind=kind, title=title, body=body,
                                                      created_at=now).on_conflict_do_nothing(index_elements=["booking_id", "kind"]))


async def after_booking(conn: AsyncConnection, *, user_id: int, booking_id: int, reference: str, film: str, starts_at: datetime,
                        zone: str, paid_paise: int, redeemed: dict | None, ratio: int, now: datetime) -> None:
    """Everything a confirmed booking writes for the account, in the booking's own transaction: the redemption's
    ledger row, the earned points, and one notification per event (CR-008 T3, T7)."""
    await notify(conn, user_id=user_id, booking_id=booking_id, kind="booking_confirmed", title=f"Booking {reference} confirmed",
                 body=f"{film}, {_when(starts_at, zone)}. Show the reference at the door.", now=now)
    if redeemed:
        await record(conn, user_id=user_id, booking_id=booking_id, kind="redeemed", points=redeemed["points"],
                     discount_paise=redeemed["discount_paise"], now=now)
        await notify(conn, user_id=user_id, booking_id=booking_id, kind="points_redeemed", title=f"{redeemed['points']:,} points used",
                     body=f"They paid for part of booking {reference}. Rewards shows the amount.", now=now)  # money is formatted
                     # at render time only (S-PAY-01): the Rewards page renders reward_entry.discount_paise
    points = await earn(conn, user_id=user_id, booking_id=booking_id, paid_paise=paid_paise, ratio=ratio, now=now)
    if points:
        await notify(conn, user_id=user_id, booking_id=booking_id, kind="points_earned", title=f"You earned {points:,} points",
                     body=f"For booking {reference}. Use them for a discount at your next checkout.", now=now)


# ---- reads for the account pages ----------------------------------------------------------------------------------


async def summary(conn: AsyncConnection, user_id: int) -> dict:
    row = (await conn.execute(select(users.c.email, users.c.display_name, users.c.points_balance,
                                     select(func.count()).select_from(notification)
                                     .where(notification.c.user_id == user_id, notification.c.read_at.is_(None))
                                     .scalar_subquery().label("unread"))
                              .where(users.c.id == user_id))).one()
    await conn.rollback()
    return {"display_name": row.display_name, "email": row.email, "points_balance": row.points_balance, "unread_notifications": row.unread}


HISTORY_MAX = 100  # ponytail: the newest 100 movements; paging is the upgrade path if an account ever has more


async def history(conn: AsyncConnection, user_id: int, ratio: int, quote_paise: int | None) -> dict:
    from app.domain.booking import presentation
    from app.models import booking

    balance = (await conn.execute(select(users.c.points_balance).where(users.c.id == user_id))).scalar_one()
    rows = (await conn.execute(select(reward_entry.c.kind, reward_entry.c.points, reward_entry.c.discount_paise,
                                      reward_entry.c.created_at, booking.c.reference)
                               .select_from(reward_entry.join(booking, reward_entry.c.booking_id == booking.c.id))
                               .where(reward_entry.c.user_id == user_id).order_by(reward_entry.c.id.desc()).limit(HISTORY_MAX))).all()
    await conn.rollback()
    out = {"points_balance": balance,
           "rules": {"earn_points_per_unit": EARN_POINTS_PER_UNIT, "redeem_points_per_unit": REDEEM_POINTS_PER_UNIT,
                     "redeem_cap_percent": 100 // REDEEM_CAP_DIVISOR},
           "history": [{"kind": r.kind, "points": r.points, "discount_paise": r.discount_paise,
                        "created_at": r.created_at.isoformat().replace("+00:00", "Z"), "booking_reference": presentation(r.reference)}
                       for r in rows]}
    if quote_paise is not None:
        out["quote"] = quote(quote_paise, balance, ratio)
    return out


INBOX_MAX = 100


async def inbox(conn: AsyncConnection, user_id: int) -> dict:
    from app.domain.booking import presentation
    from app.models import booking

    rows = (await conn.execute(select(notification.c.id, notification.c.kind, notification.c.title, notification.c.body,
                                      notification.c.read_at, notification.c.created_at, booking.c.reference)
                               .select_from(notification.join(booking, notification.c.booking_id == booking.c.id))
                               .where(notification.c.user_id == user_id).order_by(notification.c.id.desc()).limit(INBOX_MAX))).all()
    unread = (await conn.execute(select(func.count()).select_from(notification)
                                 .where(notification.c.user_id == user_id, notification.c.read_at.is_(None)))).scalar_one()
    await conn.rollback()
    return {"unread": unread, "items": [
        {"id": r.id, "kind": r.kind, "title": r.title, "body": r.body, "read": r.read_at is not None,
         "created_at": r.created_at.isoformat().replace("+00:00", "Z"), "booking_reference": presentation(r.reference)} for r in rows]}


async def mark_read(conn: AsyncConnection, user_id: int, ids: list[int] | None, now: datetime) -> int:
    """Mark the caller's own notifications read: the listed ones, or all when ids is None. Another account's id matches
    no row, because user_id is in the same WHERE. Returns the unread count afterwards."""
    async with conn.begin():
        where = [notification.c.user_id == user_id, notification.c.read_at.is_(None)]
        if ids is not None:
            where.append(notification.c.id.in_(ids))
        await conn.execute(update(notification).where(*where).values(read_at=now))
        return (await conn.execute(select(func.count()).select_from(notification)
                                   .where(notification.c.user_id == user_id, notification.c.read_at.is_(None)))).scalar_one()


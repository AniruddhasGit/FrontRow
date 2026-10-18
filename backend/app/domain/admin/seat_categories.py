"""Seat categories and their uplift (P-ADM-11). The formula itself is app/domain/pricing.py, never here.

affected_future_showtimes is P-ADM-11's one rule, computed one way for the read and the write:
COUNT(showtime WHERE starts_at + SALES_CUTOFF_MINUTES > evaluated_at), every hall (in service or not),
every film, every category. evaluated_at is the injected clock. The two evaluations are never compared.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.admin.common import (audit, check_ceiling, check_version, lock_price_ceiling, constraint_name, invalid, is_int,
                                     need_name, need_version, not_found, transaction, utc_text)
from app.models import seat, seat_category, showtime

NAME_BOUND = "Enter a category name of 1 to 40 characters."
NAME_TAKEN = "A seat category with that name already exists."
UPLIFT_WHOLE = "Enter the uplift in whole basis points. 100 basis points is 1 percent."
UPLIFT_NEGATIVE = "The uplift cannot be negative. This system has no discounts."
UPLIFT_CEILING = "That uplift is too large for this system to hold. Enter a smaller value."
GONE = "That seat category no longer exists at this address."
STALE = ("This seat category was changed by someone else while you were editing. Reload to see the current values, "
         "then make your change again. Nothing you typed has been saved.")

_seat_count = (select(func.count()).select_from(seat).where(seat.c.seat_category_id == seat_category.c.id)
               .scalar_subquery().label("seat_count"))
_ITEM = (seat_category.c.id, seat_category.c.name, seat_category.c.uplift_basis_points, _seat_count,
         seat_category.c.version)


async def affected_future_showtimes(conn: AsyncConnection, now: datetime, cutoff_minutes: int) -> dict:
    # starts_at + cutoff > now  <=>  starts_at > now - cutoff. Instant against instant; no zone involved.
    count = await conn.scalar(select(func.count()).select_from(showtime)
                              .where(showtime.c.starts_at > now - timedelta(minutes=cutoff_minutes)))
    return {"affected_future_showtimes": count, "evaluated_at_utc": utc_text(now)}


async def list_categories(conn: AsyncConnection, now: datetime, cutoff_minutes: int) -> dict:
    rows = (await conn.execute(select(*_ITEM).order_by(seat_category.c.name, seat_category.c.id))).mappings().all()
    return {"items": [dict(r) for r in rows], **await affected_future_showtimes(conn, now, cutoff_minutes)}


def _uplift(value: Any) -> int:
    if not is_int(value):
        raise invalid("uplift_basis_points", UPLIFT_WHOLE)
    if value < 0:
        raise invalid("uplift_basis_points", UPLIFT_NEGATIVE)
    return value


async def _check_uplift_ceiling(conn: AsyncConnection, uplift: int) -> None:
    # Against the HIGHEST STORED base price, not a constant (P-ADM-11 mirror bound).
    await lock_price_ceiling(conn)
    highest = await conn.scalar(select(func.coalesce(func.max(showtime.c.base_price_paise), 0)))
    if not check_ceiling(highest, uplift):
        raise invalid("uplift_basis_points", UPLIFT_CEILING)


async def _name_taken(conn: AsyncConnection, name: str, except_id: int | None = None) -> bool:
    q = select(func.count()).select_from(seat_category).where(func.lower(func.trim(seat_category.c.name)) == name.lower())
    if except_id is not None:
        q = q.where(seat_category.c.id != except_id)
    return bool(await conn.scalar(q))


def _taken(exc: IntegrityError):
    if constraint_name(exc) == "uq_seat_category__name_ci":
        return invalid("name", NAME_TAKEN)
    raise exc


async def create_category(conn: AsyncConnection, actor: Any, fields: dict, now: datetime) -> dict:
    name = need_name(fields.get("name"), "name", 40, NAME_BOUND)
    uplift = _uplift(fields.get("uplift_basis_points"))
    try:
        async with transaction(conn, ("seat_category.created",)):
            await _check_uplift_ceiling(conn, uplift)
            if await _name_taken(conn, name):
                raise invalid("name", NAME_TAKEN)
            new_id = await conn.scalar(insert(seat_category).values(name=name, uplift_basis_points=uplift, version=1)
                                       .returning(seat_category.c.id))
            await audit(conn, actor, "seat_category.created", "seat_category", new_id, None,
                        {"name": name, "uplift_basis_points": uplift}, now)
            return {"id": new_id, "name": name, "uplift_basis_points": uplift, "version": 1}
    except IntegrityError as exc:
        raise _taken(exc) from None


async def edit_category(conn: AsyncConnection, actor: Any, category_id: int, fields: dict, now: datetime,
                        cutoff_minutes: int) -> dict:
    version = need_version(fields)
    try:
        async with transaction(conn, ("seat_category.updated", "seat_category.uplift_changed")):
            row = (await conn.execute(select(seat_category).where(seat_category.c.id == category_id)
                                      .with_for_update())).mappings().first()
            if row is None:
                raise not_found(GONE)
            check_version(row["version"], version, STALE)
            changes = {}
            if "name" in fields:
                changes["name"] = need_name(fields["name"], "name", 40, NAME_BOUND)
            if "uplift_basis_points" in fields:
                changes["uplift_basis_points"] = _uplift(fields["uplift_basis_points"])
                await _check_uplift_ceiling(conn, changes["uplift_basis_points"])
            changes = {k: v for k, v in changes.items() if v != row[k]}
            new_version = row["version"]
            if changes:
                if "name" in changes and await _name_taken(conn, changes["name"], category_id):
                    raise invalid("name", NAME_TAKEN)
                new_version += 1
                await conn.execute(update(seat_category).where(seat_category.c.id == category_id)
                                   .values(**changes, version=new_version, updated_at=func.now()))
                for key, action in (("name", "seat_category.updated"), ("uplift_basis_points", "seat_category.uplift_changed")):
                    if key in changes:
                        await audit(conn, actor, action, "seat_category", category_id, {key: row[key]}, {key: changes[key]}, now)
            merged = {**row, **changes}
            return {"id": category_id, "name": merged["name"], "uplift_basis_points": merged["uplift_basis_points"],
                    **await affected_future_showtimes(conn, now, cutoff_minutes), "version": new_version}
    except IntegrityError as exc:
        raise _taken(exc) from None

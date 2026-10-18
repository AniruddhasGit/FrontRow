"""The venue (P-ADM-25, P-ADM-26): list, and edit the name and the IANA zone. No create, no delete.

The row's zone is the only authority for local time; no request-path code reads the environment's zone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.admin.common import (audit, check_version, constraint_name, invalid, need_name, need_version,
                                     not_found, transaction)
from app.models import cinema, screen, showtime

NAME_BOUND = "Enter a venue name of 1 to 120 characters."
NAME_TAKEN = "A venue with that name already exists."
ZONE_BAD = "That is not a time zone this system recognises. Enter an IANA zone name, such as Asia/Kolkata."
GONE = "That venue no longer exists at this address."
STALE = ("This venue was changed by someone else while you were editing. Reload to see the current details, "
         "then make your change again. Nothing you typed has been saved.")

_screens = select(func.count()).select_from(screen).where(screen.c.cinema_id == cinema.c.id).scalar_subquery()
_showtimes = (select(func.count()).select_from(showtime.join(screen, showtime.c.screen_id == screen.c.id))
              .where(screen.c.cinema_id == cinema.c.id).scalar_subquery())
_COLUMNS = (cinema.c.id, cinema.c.name, cinema.c.timezone, _screens.label("screen_count"),
            _showtimes.label("showtime_count"), cinema.c.version)


def _zone(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise invalid("timezone", ZONE_BAD)
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise invalid("timezone", ZONE_BAD) from None
    return value


async def list_cinemas(conn: AsyncConnection) -> dict:
    rows = (await conn.execute(select(*_COLUMNS).order_by(cinema.c.name, cinema.c.id))).mappings().all()
    return {"items": [dict(r) for r in rows]}


async def _one(conn: AsyncConnection, cinema_id: int) -> dict:
    return dict((await conn.execute(select(*_COLUMNS).where(cinema.c.id == cinema_id))).mappings().one())


async def edit_cinema(conn: AsyncConnection, actor: Any, cinema_id: int, fields: dict, now: datetime) -> dict:
    version = need_version(fields)
    try:
        async with transaction(conn, ("cinema.updated", "cinema.timezone_changed")):
            row = (await conn.execute(select(cinema).where(cinema.c.id == cinema_id).with_for_update())).mappings().first()
            if row is None:
                raise not_found(GONE)
            check_version(row["version"], version, STALE)
            changes = {}
            if "name" in fields:
                changes["name"] = need_name(fields["name"], "name", 120, NAME_BOUND)
            if "timezone" in fields:
                changes["timezone"] = _zone(fields["timezone"])
            changes = {k: v for k, v in changes.items() if v != row[k]}
            if changes:
                if "name" in changes:
                    taken = await conn.scalar(select(func.count()).select_from(cinema).where(
                        func.lower(func.trim(cinema.c.name)) == changes["name"].lower(), cinema.c.id != cinema_id))
                    if taken:
                        raise invalid("name", NAME_TAKEN)
                await conn.execute(update(cinema).where(cinema.c.id == cinema_id).values(**changes, version=row["version"] + 1))
                for key, action in (("name", "cinema.updated"), ("timezone", "cinema.timezone_changed")):
                    if key in changes:
                        await audit(conn, actor, action, "cinema", cinema_id, {key: row[key]}, {key: changes[key]}, now)
            return await _one(conn, cinema_id)
    except IntegrityError as exc:
        if constraint_name(exc) == "uq_cinema__name_ci":
            raise invalid("name", NAME_TAKEN) from None
        raise

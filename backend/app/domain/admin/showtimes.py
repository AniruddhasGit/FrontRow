"""Showtimes, created by hand and only by hand (P-ADM-07 to P-ADM-10, P-ADM-14's seat set).

Create and edit run inside a row lock (with_for_update) on the screen row: that lock is what serialises the
overlap check (no constraint can say "these two ranges overlap") and what makes the seat set exactly
the in-service seats at that instant. The intervals are half-open: [starts_at, ends_at).

Times arrive and leave as NAIVE LOCAL in the cinema row's zone (E6 S4, P-ADM-26); storage is UTC.
ends_at is stored, never derived from the film's runtime.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import BigInteger, and_, func, insert, literal, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.domain.admin.common import (DB_DOWN, audit, check_ceiling, check_version, lock_price_ceiling, invalid, is_int, need_int,
                                     need_version, not_found, parse_local, to_local, to_utc, transaction)
from app.domain.admin.halls import lock_screen
from app.models import booking_seat, cinema, format, movie, screen, seat, seat_category, showtime, showtime_seat

FILM_GONE = "That film no longer exists. Choose a film from the list."
HALL_GONE = "That hall no longer exists. Choose a hall from the list."
HALL_GONE_HERE = "That hall no longer exists at this address."
SHOWTIME_GONE = "That showtime no longer exists at this address."
HALL_OUT = "This hall is out of service. Bring it back into service before creating showtimes on it."
NO_SEATS = "This hall has no seats in service. Add seats before creating a showtime on it."
END_AFTER_START = "The showtime must end after it starts."
OUTSIDE_WINDOW = ("This film's display window does not cover that start time. Change the time, or widen the film's "
                  "window first.")
NO_MOVE = "A showtime cannot be moved to a different hall. Create the showtime on the other hall instead."
STALE = ("This showtime was changed by someone else while you were editing. Reload to see the current details, "
         "then make your change again. Nothing you typed has been saved.")
PRICE_MISSING = "Enter a base price for this showtime."
PRICE_WHOLE = "Enter the base price in whole paise. A price cannot have a fraction of a paisa."
PRICE_LOW = "The base price must be at least 1 paisa."
PRICE_CEILING = "That base price is too large for this system to hold. Enter a smaller amount."
BAD_DATE = "That date is not valid."
BAD_FILTER = "That filter value is not valid."


def _price(value: Any) -> int:
    if value is None:
        raise invalid("base_price_paise", PRICE_MISSING)
    if type(value) is not int:
        raise invalid("base_price_paise", PRICE_WHOLE)  # 25000.5 is refused, never rounded (FR-ADR-036)
    if value < 1:
        raise invalid("base_price_paise", PRICE_LOW)
    if not is_int(value):
        raise invalid("base_price_paise", PRICE_CEILING)  # past bigint: certainly past the ceiling
    return value


async def _check_price_ceiling(conn: AsyncConnection, price: int) -> None:
    # Against the HIGHEST STORED uplift, not a constant (P-ADM-10).
    await lock_price_ceiling(conn)
    highest = await conn.scalar(select(func.coalesce(func.max(seat_category.c.uplift_basis_points), 0)))
    if not check_ceiling(price, highest):
        raise invalid("base_price_paise", PRICE_CEILING)


async def _zone(conn: AsyncConnection, screen_id: int) -> str:
    """showtime -> screen -> cinema.timezone: the only authority for local time (P-ADM-26)."""
    return await conn.scalar(select(cinema.c.timezone).select_from(screen.join(cinema, screen.c.cinema_id == cinema.c.id))
                             .where(screen.c.id == screen_id))


async def _check_format(conn: AsyncConnection, format_id: Any) -> None:
    if format_id is None:
        return
    active = is_int(format_id) and await conn.scalar(select(format.c.is_active).where(format.c.id == format_id))
    if not active:
        raise invalid("format_id")


def _check_window(film: dict, starts_utc: datetime) -> None:
    lo, hi = film["display_from"], film["display_until"]
    if lo is not None and hi is not None and not (lo <= starts_utc < hi):
        raise invalid("starts_at", OUTSIDE_WINDOW)


def _clock(t: datetime) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"


async def _check_overlap(conn: AsyncConnection, screen_row: dict, starts: datetime, ends: datetime, zone: str,
                         this_id: int | None = None) -> None:
    """P-ADM-08's predicate: starts_at < :new_ends_at AND ends_at > :new_starts_at [AND id <> :this_id]."""
    where = [showtime.c.screen_id == screen_row["id"], showtime.c.starts_at < ends, showtime.c.ends_at > starts]
    if this_id is not None:
        where.append(showtime.c.id != this_id)
    rows = (await conn.execute(select(showtime.c.id, movie.c.title, showtime.c.starts_at, showtime.c.ends_at)
                               .select_from(showtime.join(movie, showtime.c.movie_id == movie.c.id))
                               .where(and_(*where)).order_by(showtime.c.starts_at, showtime.c.id))).all()
    if not rows:
        return
    hall = screen_row["name"]
    if len(rows) == 1:
        s, e = (r.astimezone(ZoneInfo(zone)) for r in (rows[0].starts_at, rows[0].ends_at))
        message = (f"{hall} already has a showtime from {_clock(s)} to {_clock(e)} on {s.day} {s:%b %Y}. Two showtimes "
                   "cannot run in one hall at the same time. Choose a different time or a different hall.")
    else:
        message = (f"{hall} already has {len(rows)} showtimes in that period. Two showtimes cannot run in one hall at "
                   "the same time. Choose a different time or a different hall.")
    conflicts = [{"showtime_id": r.id, "movie_title": r.title, "starts_at": to_local(r.starts_at, zone),
                  "ends_at": to_local(r.ends_at, zone)} for r in rows]
    raise ApiError(409, "SHOWTIME_OVERLAP", message, {"conflicts": conflicts})


async def write_seat_set(conn: AsyncConnection, showtime_id: int, screen_id: int) -> int:
    """One statement, inside the screen lock: the showtime's seats are the in-service seats at this instant,
    for the rest of its life (P-ADM-14). Returns the number of rows written."""
    result = await conn.execute(insert(showtime_seat).from_select(
        ["showtime_id", "seat_id"],
        select(literal(showtime_id, BigInteger()), seat.c.id)
        .where(seat.c.screen_id == screen_id, seat.c.is_active.is_(True))).returning(showtime_seat.c.seat_id))
    # Counted from the rows the statement returned: the async driver reports rowcount -1 for INSERT ... SELECT.
    return len(result.all())


def _out(row: dict, zone: str) -> dict:
    return {"id": row["id"], "movie_id": row["movie_id"], "screen_id": row["screen_id"],
            "starts_at": to_local(row["starts_at"], zone), "ends_at": to_local(row["ends_at"], zone),
            "base_price_paise": row["base_price_paise"], "format_id": row["format_id"],
            "seat_count_at_creation": row["seat_count_at_creation"], "version": row["version"]}


async def create_showtime(conn: AsyncConnection, actor: Any, fields: dict, now: datetime) -> dict:
    movie_id = need_int(fields.get("movie_id"), "movie_id")
    screen_id = need_int(fields.get("screen_id"), "screen_id")
    starts_local = parse_local(fields.get("starts_at"), "starts_at", END_AFTER_START)
    ends_local = parse_local(fields.get("ends_at"), "ends_at", END_AFTER_START)
    if ends_local <= starts_local:
        raise invalid("ends_at", END_AFTER_START)
    price = _price(fields.get("base_price_paise"))
    format_id = fields.get("format_id")
    async with transaction(conn, ("showtime.created",)):
        hall = await lock_screen(conn, screen_id)
        film = (await conn.execute(select(movie).where(movie.c.id == movie_id))).mappings().first()
        if film is None:
            raise not_found(FILM_GONE)
        if hall is None:
            raise not_found(HALL_GONE)
        if not hall["is_active"]:
            raise ApiError(409, "LAYOUT_FROZEN", HALL_OUT)
        in_service = await conn.scalar(select(func.count()).select_from(seat)
                                       .where(seat.c.screen_id == screen_id, seat.c.is_active.is_(True)))
        if in_service == 0:
            raise ApiError(409, "LAYOUT_FROZEN", NO_SEATS)  # no showtime may carry a zero denominator
        await _check_format(conn, format_id)
        await _check_price_ceiling(conn, price)
        zone = await _zone(conn, screen_id)
        starts, ends = to_utc(starts_local, zone), to_utc(ends_local, zone)
        _check_window(film, starts)
        await _check_overlap(conn, hall, starts, ends, zone)
        new_id = await conn.scalar(insert(showtime).values(
            movie_id=movie_id, screen_id=screen_id, starts_at=starts, ends_at=ends, base_price_paise=price,
            format_id=format_id, seat_count_at_creation=0, version=1).returning(showtime.c.id))
        try:
            written = await write_seat_set(conn, new_id, screen_id)
        except DBAPIError as exc:  # P-ADM-14 exception 2: the pair is atomic, so nothing is saved
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", DB_DOWN) from exc
        await conn.execute(update(showtime).where(showtime.c.id == new_id).values(seat_count_at_creation=written))
        row = dict((await conn.execute(select(showtime).where(showtime.c.id == new_id))).mappings().one())
        await audit(conn, actor, "showtime.created", "showtime", new_id, None,
                    {"movie_id": movie_id, "screen_id": screen_id, "starts_at": starts.isoformat(),
                     "ends_at": ends.isoformat(), "base_price_paise": price, "format_id": format_id,
                     "seat_count_at_creation": written}, now)
        return _out(row, zone)


_EDITABLE = ("movie_id", "starts_at", "ends_at", "base_price_paise", "format_id")


async def edit_showtime(conn: AsyncConnection, actor: Any, showtime_id: int, fields: dict, now: datetime) -> dict:
    version = need_version(fields)
    async with transaction(conn, ("showtime.updated", "showtime.base_price_changed")):
        screen_id = await conn.scalar(select(showtime.c.screen_id).where(showtime.c.id == showtime_id))
        if screen_id is None:
            raise not_found(SHOWTIME_GONE)
        hall = await lock_screen(conn, screen_id)
        row = dict((await conn.execute(select(showtime).where(showtime.c.id == showtime_id).with_for_update()))
                   .mappings().one())
        check_version(row["version"], version, STALE)
        if "screen_id" in fields and fields["screen_id"] != row["screen_id"]:
            raise invalid("screen_id", NO_MOVE)
        zone = await _zone(conn, screen_id)
        wanted: dict[str, Any] = {}
        if "movie_id" in fields:
            wanted["movie_id"] = need_int(fields["movie_id"], "movie_id")
        for key in ("starts_at", "ends_at"):
            if key in fields:
                wanted[key] = to_utc(parse_local(fields[key], key, END_AFTER_START), zone)
        if "base_price_paise" in fields:
            wanted["base_price_paise"] = _price(fields["base_price_paise"])
            await _check_price_ceiling(conn, wanted["base_price_paise"])
        if "format_id" in fields:
            await _check_format(conn, fields["format_id"])
            wanted["format_id"] = fields["format_id"]
        merged = {**row, **wanted}
        if merged["ends_at"] <= merged["starts_at"]:  # the bound is on the MERGED row (E6 S4)
            raise invalid("ends_at", END_AFTER_START)
        film = None
        if "movie_id" in wanted:
            film = (await conn.execute(select(movie).where(movie.c.id == merged["movie_id"]))).mappings().first()
            if film is None:
                raise not_found(FILM_GONE)
        if {"movie_id", "starts_at"} & set(wanted):
            film = film or (await conn.execute(select(movie).where(movie.c.id == merged["movie_id"]))).mappings().one()
            _check_window(film, merged["starts_at"])
        if {"starts_at", "ends_at"} & set(wanted):
            await _check_overlap(conn, hall, merged["starts_at"], merged["ends_at"], zone, this_id=showtime_id)
        changes = {k: v for k, v in wanted.items() if v != row[k]}
        if changes:  # nothing changed -> 200, nothing written, version unchanged (P-ADM-12)
            merged["version"] = row["version"] + 1
            await conn.execute(update(showtime).where(showtime.c.id == showtime_id).values(**changes, version=merged["version"]))
            if "base_price_paise" in changes:
                await audit(conn, actor, "showtime.base_price_changed", "showtime", showtime_id,
                            {"base_price_paise": row["base_price_paise"]}, {"base_price_paise": changes["base_price_paise"]}, now)
            other = {k: v for k, v in changes.items() if k != "base_price_paise"}
            if other:
                text = lambda v: v.isoformat() if isinstance(v, datetime) else v  # noqa: E731
                await audit(conn, actor, "showtime.updated", "showtime", showtime_id,
                            {k: text(row[k]) for k in other}, {k: text(v) for k, v in other.items()}, now)
        else:
            merged = row
        return _out(merged, zone)


def _parse_screen_id(value: str | None) -> int:
    if not (value and value.isascii() and value.isdigit() and int(value) > 0):
        raise invalid("screen_id", HALL_GONE)
    return int(value)


async def list_day(conn: AsyncConnection, screen_id: str | None, day: str | None, include_past: str | None,
                   now: datetime) -> dict:
    """EP-ADM-09: one hall's whole local day, filtered by include_past BEFORE anything else, never paged.
    Past means starts_at <= now, the request instant taken once (P-ADM-09)."""
    sid = _parse_screen_id(screen_id)
    try:
        local_day = date.fromisoformat(day) if day is not None and len(day) == 10 else None
    except ValueError:
        local_day = None
    if local_day is None:
        raise invalid("date", BAD_DATE)
    if include_past not in (None, "true", "false"):
        raise invalid("include_past", BAD_FILTER)
    if await conn.scalar(select(screen.c.id).where(screen.c.id == sid)) is None:
        raise not_found(HALL_GONE_HERE)
    zone = await _zone(conn, sid)
    lo = to_utc(datetime.combine(local_day, datetime.min.time()), zone)
    hi = to_utc(datetime.combine(local_day + timedelta(days=1), datetime.min.time()), zone)
    booked = (select(func.count()).select_from(booking_seat).where(booking_seat.c.showtime_id == showtime.c.id)
              .scalar_subquery())
    q = (select(showtime.c.id, showtime.c.movie_id, movie.c.title.label("movie_title"), showtime.c.starts_at,
                showtime.c.ends_at, showtime.c.base_price_paise, showtime.c.seat_count_at_creation,
                booked.label("booked_seat_count"), showtime.c.version)
         .select_from(showtime.join(movie, showtime.c.movie_id == movie.c.id))
         .where(showtime.c.screen_id == sid, showtime.c.starts_at >= lo, showtime.c.starts_at < hi))
    if include_past == "false":
        q = q.where(showtime.c.starts_at > now)
    rows = (await conn.execute(q.order_by(showtime.c.starts_at, showtime.c.id))).mappings().all()
    return {"items": [{**r, "starts_at": to_local(r["starts_at"], zone), "ends_at": to_local(r["ends_at"], zone)}
                      for r in rows]}

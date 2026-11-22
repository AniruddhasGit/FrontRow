"""CR-006: the demo schedule never runs out. No timer and no scheduled job (SRC-003: nothing runs on a schedule):
the public listing calls top_up(), at most once an hour per Redis key, and only when DEMO_SHOWTIMES_AHEAD_DAYS > 0
(the Render demo copy; the AWS copy leaves it 0 and nothing here ever runs).

When the last showtime starts less than (horizon - 7) days from now, the last 7 days of the schedule are copied 7
days forward until the schedule reaches the horizon. Each copy keeps its hall, local slot, price and format, and
moves to the NEXT published film in id order that is released by that show's day (CR-008 T10: a film coming soon gets
no show before its release date), so the same films keep rotating. Its end keeps the copied show's
gap after the film: ends = starts + (old ends - old starts) - old runtime + new runtime. Each film's display_until is pushed
to cover its new showtimes (the listing's visibility window). Seat sets are written by the admin path's own
write_seat_set. One Postgres advisory lock makes concurrent visitors a single top-up.

Not audited: there is no actor (S-ADM-02 forbids an audit row without one); the log line is the record.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.admin.showtimes import write_seat_set
from app.domain.browse.catalogue import default_zone, load_zones
from app.models import movie, showtime

log = logging.getLogger("app.schedule")
WEEK = timedelta(days=7)
LOCK = 7_260_301  # pg_advisory_xact_lock key for the top-up; any constant no other code uses


async def delete_history(conn: AsyncConnection, now: datetime, days: int) -> int:
    """CR-006 (owner ruling 2026-11-22): the demo deletes the seat rows of showtimes older than `days`, and those old
    showtimes no booking references, through the one SECURITY DEFINER function (migration 0004). Bookings are never
    touched, and the app role itself holds no DELETE grant. Returns the number of showtimes deleted."""
    async with conn.begin():
        gone = await conn.scalar(text("SELECT demo_delete_history(:cutoff)"), {"cutoff": now - timedelta(days=days)})
    if gone:
        log.info("demo history deleted", extra={"showtimes_deleted": gone, "older_than_days": days})
    return gone or 0


async def top_up(conn: AsyncConnection, now: datetime, horizon_days: int) -> int:
    """Returns the number of showtimes added (0 when the schedule already reaches far enough)."""
    horizon = now + timedelta(days=horizon_days)
    async with conn.begin():
        await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK})
        last = await conn.scalar(select(func.max(showtime.c.starts_at)))
        if last is None or last >= horizon - WEEK:
            return 0
        released = dict((await conn.execute(
            select(movie.c.id, movie.c.release_date).where(movie.c.published_at.is_not(None)).order_by(movie.c.id))).all())
        films = list(released)
        zone = ZoneInfo(default_zone(await load_zones(conn)))

        def next_film(after: int, starts: datetime) -> int:
            day = starts.astimezone(zone).date()
            start = films.index(after) + 1 if after in films else 0
            for k in range(len(films)):
                film = films[(start + k) % len(films)]
                if released[film] is None or released[film] <= day:
                    return film
            return after
        runtime = dict((await conn.execute(select(movie.c.id, movie.c.runtime_minutes))).all())
        added, reach = 0, {}
        # After a long quiet spell the schedule may have ended long ago: jump in whole 7-day steps so the first copy
        # lands in the current week, instead of filling the past.
        shift = WEEK * max(1, (now - last) // WEEK + 1)
        while last < horizon - WEEK:
            week = (await conn.execute(select(showtime).where(showtime.c.starts_at > last - WEEK, showtime.c.starts_at <= last)
                                       .order_by(showtime.c.starts_at))).mappings().all()
            for s in week:
                starts = s["starts_at"] + shift
                film = next_film(s["movie_id"], starts) if s["movie_id"] in films else s["movie_id"]
                ends = starts + (s["ends_at"] - s["starts_at"]) + timedelta(minutes=runtime[film] - runtime[s["movie_id"]])
                new_id = await conn.scalar(insert(showtime).values(
                    movie_id=film, screen_id=s["screen_id"], starts_at=starts, ends_at=ends,
                    base_price_paise=s["base_price_paise"], format_id=s["format_id"], seat_count_at_creation=0,
                    version=1).returning(showtime.c.id))
                written = await write_seat_set(conn, new_id, s["screen_id"])
                await conn.execute(update(showtime).where(showtime.c.id == new_id).values(seat_count_at_creation=written))
                reach[film] = max(reach.get(film, starts), starts)
                added += 1
            last += shift
            shift = WEEK
        for film, until in reach.items():  # the film stays visible through its last new showtime's day
            await conn.execute(update(movie).where(movie.c.id == film, movie.c.display_until < until + timedelta(days=1))
                               .values(display_until=until + timedelta(days=1), version=movie.c.version + 1))
    log.info("demo schedule topped up", extra={"showtimes_added": added, "horizon_days": horizon_days})
    return added

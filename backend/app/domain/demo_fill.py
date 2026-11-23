"""The demo copy's crowd (owner, 2026-11-23): every show already has seats sold, filling up as it approaches, so the seat
map never looks empty and the manager and admin figures have sales to show. Only when DEMO_SHOWTIMES_AHEAD_DAYS > 0
(the Render demo; AWS leaves it 0 and nothing here runs). No timer and no job (SRC-003): the public listing's hourly
schedule check (api/browse.py _top_up, one Redis key an hour) calls fill() after top_up(), and the owner's one-off
backfill is scripts/demo_bookings.py.

THE TARGET. A show's share of seats sold at time T is final(show) * ramp(days until it starts). final is fixed per show
(a hash of its id, never random): about 0.82 on a weekday afternoon, more for Friday to Sunday and for evenings, less
for a morning, with about 1 show in 12 nearly sold out and 1 in 14 weak; across many shows it averages 80-90%.
ramp = 0.08 + 0.92 * exp(-days / 5.5): ~10% three weeks out, ~34% a week out, ~72% two days out, 100% at the start.

THE SEATS. Free seats are ranked by how good they are (near the centre column, about 60% of the way back, a premium or
recliner seat first) plus a per-show jitter, and taken in groups of 1 to 6 side by side in one row, mostly pairs. Each
group is one booking by one demo crowd account, dated between when the ramp reached the show's previous level and now.

THE GUARANTEE. Every booked seat is a real booking (app/domain/booking insert_demo_bookings): payment, booking,
booking_seat, receipt_dispatch, counted by the reports like any sale. Before the insert each chosen seat's own hold lock
is taken with the hold path's SET NX PX (app/core/locks.py), so a seat a customer holds is skipped, never taken; the
UNIQUE (showtime_id, seat_id) stays the guard behind it. Without Redis (the backfill run with no REDIS_URL) the lock
step is skipped and the UNIQUE alone guards: a customer mid-checkout on a seat the backfill took gets "someone took that
seat", never a double sale. A customer can always hold and book any seat still free.

ponytail: one transaction per call under one advisory lock, so a listing read and the backfill never fill the same
show twice. Bounded per call by `cap` seats, nearest shows first; a show is skipped until it is at least 2 seats short,
so the hourly call writes a few seats per show, not a trickle of single rows.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, and_, case, cast, exists, false, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import cache, locks
from app.domain import reference
from app.domain.booking import insert_demo_bookings
from app.domain.browse.catalogue import default_zone, load_zones
from app.models import booking_seat, movie, seat, seat_category, showtime, showtime_seat, users

log = logging.getLogger("app.demo_fill")
LOCK = 7_260_302  # pg_advisory_xact_lock key for the fill (schedule.py's top-up uses 7_260_301)
# The demo crowd: customer-51@ onward at a .invalid domain (RFC 2606, never deliverable), created by
# scripts/demo_reviews.py with the seed's email pattern. customer-01..50 are the seed's own logins and stay untouched.
CROWD_FIRST = 51
CROWD_SIZE = 700
CAP = 4000  # seats per call on the listing path: a few seconds of bulk insert at most, once an hour
LOOKBACK = timedelta(days=1)  # a show that started within this is still brought to its final share
STEP = 2  # a show is filled once it is at least this many seats short of its target
LOCK_TTL_MS = 30_000  # the fill's own seat locks: long enough for its transaction, gone on their own after
GROUPS = (1, 2, 3, 4, 5, 6)
GROUP_WEIGHTS = (12, 40, 14, 20, 7, 7)  # mostly pairs and fours


def crowd():
    """THE crowd-account predicate on users (CR-013: also the review badge's demo half). The number is cast only once the
    pattern has matched (a CASE, since Postgres may reorder an AND), so no other email can make the cast fail."""
    number = func.split_part(func.substr(users.c.email, 10), "@", 1)
    return and_(users.c.role == "customer",
                case((users.c.email.op("~")(r"^customer-[0-9]+@[^@]+[.]invalid$"), cast(number, Integer) >= CROWD_FIRST),
                     else_=false()))


def crowd_statement():
    return select(users.c.id).where(crowd()).order_by(users.c.id)


def _unit(*key: object) -> float:
    """A stable number in [0, 1) from the key: the same show gets the same answer on every run and every machine."""
    return int.from_bytes(hashlib.blake2b(":".join(map(str, key)).encode(), digest_size=8).digest(), "big") / 2**64


def final_share(showtime_id: int, starts_local: datetime) -> float:
    """The share of seats sold by the time the show starts."""
    share = 0.82 + (0.06 if starts_local.weekday() >= 4 else 0.0)
    share += 0.05 if starts_local.hour >= 17 else (-0.08 if starts_local.hour < 13 else 0.0)
    share += (_unit("final", showtime_id) - 0.5) * 0.20
    tail = _unit("tail", showtime_id)
    if tail < 0.08:
        share = 0.96 + 0.04 * _unit("full", showtime_id)  # nearly sold out
    elif tail > 0.93:
        share = 0.50 + 0.15 * _unit("weak", showtime_id)  # a weak show
    return min(1.0, max(0.35, share))


def ramp(days: float) -> float:
    return 1.0 if days <= 0 else 0.08 + 0.92 * math.exp(-days / 5.5)


def _days_at(level: float) -> float:
    """ramp's inverse: how many days before the start the ramp stood at `level` (30 when it never stood that low)."""
    if level >= 1.0:
        return 0.0
    if level <= 0.08 + 0.92 * math.exp(-30 / 5.5):
        return 30.0
    return -5.5 * math.log((level - 0.08) / 0.92)


def target_share(showtime_id: int, starts_at: datetime, now: datetime, zone: ZoneInfo) -> float:
    return final_share(showtime_id, starts_at.astimezone(zone)) * ramp((starts_at - now).total_seconds() / 86400)


def choose(seats: list[tuple[int, int, int, int, int]], need: int, rng: random.Random, salt: int) -> list[list[tuple]]:
    """Groups of free seats side by side, best seats first. seats: (seat_id, row, col, category_id, uplift_bp) of the
    FREE seats only. Returns at most `need` seats in groups."""
    if not seats or need <= 0:
        return []
    rows, cols = [s[1] for s in seats], [s[2] for s in seats]
    centre, half = (min(cols) + max(cols)) / 2, max(1.0, (max(cols) - min(cols)) / 2)
    best_row, depth = min(rows) + 0.6 * (max(rows) - min(rows)), max(1.0, max(rows) - min(rows))

    def rank(s) -> float:
        return (abs(s[2] - centre) / half + 0.7 * abs(s[1] - best_row) / depth - (0.35 if s[4] > 0 else 0.0)
                + 0.6 * _unit("seat", salt, s[0]))
    free = {(s[1], s[2]): s for s in seats}
    groups: list[list[tuple]] = []
    for s in sorted(seats, key=rank):
        if need <= 0:
            break
        if (s[1], s[2]) not in free:
            continue
        size = min(rng.choices(GROUPS, GROUP_WEIGHTS)[0], need)
        group, lo, hi = [free.pop((s[1], s[2]))], s[2], s[2]
        while len(group) < size:  # grow to whichever side is nearer the centre, then the other; a gap ends it
            sides = sorted((hi + 1, lo - 1), key=lambda c: abs(c - centre))
            nxt = next((c for c in sides if (s[1], c) in free), None)
            if nxt is None:
                break
            group.append(free.pop((s[1], nxt)))
            lo, hi = min(lo, nxt), max(hi, nxt)
        groups.append(group)
        need -= len(group)
    return groups


async def fill(conn: AsyncConnection, redis, now: datetime, *, horizon_days: int, since: timedelta = LOOKBACK,
               cap: int | None = CAP, draw: Callable[[], str] = reference.new_reference) -> int:
    """Bring every published film's shows starting in [now - since, now + horizon_days) up to their target share, in
    ONE transaction. Returns the number of seats booked. `redis` None skips the seat locks (the backfill without Redis)."""
    taken_locks: list[tuple[str, str]] = []
    touched: set[int] = set()
    try:
        async with conn.begin():
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK})
            zone = ZoneInfo(default_zone(await load_zones(conn)))
            crowd = (await conn.execute(crowd_statement())).scalars().all()
            if not crowd:
                return 0
            capacity = (select(func.count()).select_from(showtime_seat.join(seat, and_(seat.c.id == showtime_seat.c.seat_id,
                                                                                         seat.c.is_active)))
                        .where(showtime_seat.c.showtime_id == showtime.c.id).scalar_subquery())
            sold = select(func.count()).select_from(booking_seat).where(booking_seat.c.showtime_id == showtime.c.id).scalar_subquery()
            shows = (await conn.execute(
                select(showtime.c.id, showtime.c.starts_at, showtime.c.created_at, showtime.c.base_price_paise,
                       capacity.label("capacity"), sold.label("sold"))
                .select_from(showtime.join(movie, movie.c.id == showtime.c.movie_id))
                .where(movie.c.published_at.is_not(None), showtime.c.starts_at >= now - since,
                       showtime.c.starts_at < now + timedelta(days=horizon_days))
                .order_by(showtime.c.starts_at, showtime.c.id))).all()
            plan, budget = [], cap
            for s in shows:
                need = round(s.capacity * target_share(s.id, s.starts_at, now, zone)) - s.sold
                if need < STEP:
                    continue
                if budget is not None:
                    if budget <= 0:
                        break
                    need = min(need, budget)
                    budget -= need
                plan.append((s, need))
            if not plan:
                return 0
            free: dict[int, list[tuple]] = {}
            booked = exists(select(booking_seat.c.id).where(booking_seat.c.showtime_id == showtime_seat.c.showtime_id,
                                                           booking_seat.c.seat_id == seat.c.id))
            for show_id, seat_id, row, col, cat, uplift in (await conn.execute(
                    select(showtime_seat.c.showtime_id, seat.c.id, seat.c.grid_row, seat.c.grid_col, seat.c.seat_category_id,
                           seat_category.c.uplift_basis_points)
                    .select_from(showtime_seat.join(seat, seat.c.id == showtime_seat.c.seat_id)
                                 .join(seat_category, seat_category.c.id == seat.c.seat_category_id))
                    .where(showtime_seat.c.showtime_id.in_([s.id for s, _ in plan]), seat.c.is_active, ~booked))).all():
                free.setdefault(show_id, []).append((seat_id, row, col, cat, uplift))
            wanted = []
            for s, need in plan:
                rng = random.Random(f"{s.id}:{s.sold}")
                groups = choose(free.get(s.id, []), need, rng, s.id)
                if redis is not None and groups:
                    token = f"demo-fill-{secrets.token_hex(8)}"
                    keys = [locks.seat_key(s.id, g[0]) for group in groups for g in group]
                    async with redis.pipeline(transaction=False) as pipe:
                        for key in keys:
                            pipe.execute_command("SET", key, token, "NX", "PX", LOCK_TTL_MS)
                        won = {k for k, ok in zip(keys, await pipe.execute()) if ok}
                    taken_locks += [(k, token) for k in won]
                    groups = [[g for g in group if locks.seat_key(s.id, g[0]) in won] for group in groups]
                # Booked between the moment the ramp stood at this show's previous level and now (never after the start).
                level = s.sold / max(1, s.capacity) / final_share(s.id, s.starts_at.astimezone(zone))
                hi = min(now, s.starts_at)
                lo = min(hi, max(s.starts_at - timedelta(days=_days_at(level)), s.created_at))
                for group in groups:
                    if group:
                        at = lo + (hi - lo) * rng.random()
                        wanted.append({"user_id": crowd[rng.randrange(len(crowd))], "showtime_id": s.id,
                                       "base_price_paise": s.base_price_paise, "at": at.replace(microsecond=0),
                                       "seats": [(g[0], g[3], g[4]) for g in group]})
                        touched.add(s.id)
            written = await insert_demo_bookings(conn, wanted, draw)
    except IntegrityError:
        # A customer's booking committed on one of these seats between the read and the insert: the UNIQUE did its job.
        # Nothing was written; the next hourly call tries again.
        log.info("demo fill lost a seat to a customer; rolled back, retried on the next call")
        return 0
    finally:
        if redis is not None and taken_locks:
            async with redis.pipeline(transaction=False) as pipe:  # compare-and-delete: only our own token is removed
                for key, token in taken_locks:
                    pipe.eval(locks.RELEASE, 1, key, token)
                await pipe.execute()
    if redis is not None and touched:
        await redis.delete(*[cache.seatmap_key(i) for i in touched])  # as a booking does, after commit
    log.info("demo fill", extra={"seats_booked": written, "shows": len(touched)})
    return written

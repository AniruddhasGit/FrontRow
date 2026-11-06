"""The reporting figures (E7, P-RPT-01..12): every one computed LIVE from showtime, booking, payment and booking_seat
on every request. Nothing is precomputed, materialised or cached (P-RPT-12).

TIME. The window is a whole local day, ISO week (Monday-first) or calendar month in the cinema row's zone, converted
to UTC here in Python from the injected clock's instant; both edges reach SQL only as bound parameters, so the
database's own clock decides nothing (P-RPT-01). Half-open: starts_at >= lo AND starts_at < hi.

MONEY. Takings sum the per-seat prices snapshotted on booking_seat (FR-ADR-039), confirmed bookings whose payment is
captured only, COALESCE'd to 0 and cast back to bigint inside the SQL so no Decimal reaches the JSON (GOTCHAS).

OCCUPANCY. Capacity-weighted: total sold over the SUM of seat_count_at_creation of the same showtimes, integer half-up
to tenths, (sold * 2000 + cap) // (2 * cap) - never the mean of per-show percentages (P-RPT-04).

SCOPE. `ids` is the screen predicate's list, or None for no predicate (an admin). An EMPTY list never reaches here:
the handler short-circuits first, so no `IN ()` can be dropped into an unfiltered query (P-RPT-02).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

FILM_CAP = 100  # P-RPT-05


class BadShowtime(Exception):
    """A showtime whose seat_count_at_creation is not positive: a data defect, never a percentage (P-RPT-04 row 1)."""


def window(period: str, anchor: date) -> tuple[date, date]:
    """The local period containing `anchor`, as [first day, first day after)."""
    if period == "day":
        return anchor, anchor + timedelta(days=1)
    if period == "week":
        monday = anchor - timedelta(days=anchor.weekday())
        return monday, monday + timedelta(days=7)
    first = anchor.replace(day=1)
    return first, (first + timedelta(days=32)).replace(day=1)


def utc_midnight(day: date, zone: str) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)


def utc_text(instant: datetime) -> str:
    """A boundary instant: bare UTC, whole seconds, Z (the _utc fields; never rendered)."""
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_text(instant: datetime, zone: str) -> str:
    """A rendered instant: ISO-8601 with the cinema's offset (starts_at, occurred_at)."""
    return instant.astimezone(ZoneInfo(zone)).isoformat(timespec="seconds")


def occupancy(sold: int, capacity: int) -> float | None:
    """Tenths of a per cent, half-up, integer arithmetic; None when nothing was scheduled (never 0.0)."""
    if capacity == 0:
        return None
    return ((sold * 2000 + capacity) // (2 * capacity)) / 10


def _per_show(ids: tuple[int, ...] | None) -> str:
    """One row per in-window, in-scope showtime with its own sold count and takings. Driven from showtime on
    (screen_id, starts_at); joins payment as p.id = b.payment_id (the foreign key's direction, P-RPT-12)."""
    scope = "" if ids is None else "AND st.screen_id = ANY(:screen_ids)"
    return f"""
        SELECT st.id, st.movie_id, st.screen_id, st.starts_at, st.seat_count_at_creation AS capacity,
               count(bs.id) AS sold, CAST(COALESCE(SUM(bs.price_paise), 0) AS bigint) AS takings
        FROM showtime st
        LEFT JOIN (booking b
                   JOIN payment p ON p.id = b.payment_id AND p.state = 'captured'
                   JOIN booking_seat bs ON bs.booking_id = b.id)
               ON b.showtime_id = st.id AND b.status = 'confirmed'
        WHERE st.starts_at >= :lo AND st.starts_at < :hi {scope}
        GROUP BY st.id"""


def _params(lo: datetime, hi: datetime, ids: tuple[int, ...] | None, **more) -> dict:
    return {"lo": lo, "hi": hi, **({} if ids is None else {"screen_ids": list(ids)}), **more}


async def headline(conn: AsyncConnection, lo: datetime, hi: datetime, ids: tuple[int, ...] | None) -> dict:
    row = (await conn.execute(text(f"""
        WITH s AS ({_per_show(ids)})
        SELECT count(*) AS shows,
               CAST(COALESCE(SUM(capacity), 0) AS bigint) AS capacity,
               CAST(COALESCE(SUM(sold), 0) AS bigint) AS seats_sold,
               CAST(COALESCE(SUM(takings), 0) AS bigint) AS takings_paise,
               count(*) FILTER (WHERE capacity IS NULL OR capacity <= 0) AS bad
        FROM s"""), _params(lo, hi, ids))).one()
    if row.bad:
        raise BadShowtime()
    return {"takings_paise": row.takings_paise, "seats_sold": row.seats_sold, "capacity": row.capacity,
            "occupancy_pct": occupancy(row.seats_sold, row.capacity), "shows": row.shows}


async def films(conn: AsyncConnection, lo: datetime, hi: datetime, ids: tuple[int, ...] | None) -> tuple[list[dict], bool]:
    """The per-film rows under a TOTAL order (takings DESC, title, movie_id) and the 100-row cap. One row more than
    the cap is fetched only to know whether the cap fired."""
    rows = (await conn.execute(text(f"""
        WITH s AS ({_per_show(ids)})
        SELECT s.movie_id, m.title, count(*) AS shows,
               CAST(SUM(s.sold) AS bigint) AS seats_sold, CAST(SUM(s.capacity) AS bigint) AS capacity,
               CAST(SUM(s.takings) AS bigint) AS takings_paise
        FROM s JOIN movie m ON m.id = s.movie_id
        GROUP BY s.movie_id, m.title
        ORDER BY takings_paise DESC, m.title ASC, s.movie_id ASC
        LIMIT :cap"""), _params(lo, hi, ids, cap=FILM_CAP + 1))).all()
    out = [{"movie_id": r.movie_id, "title": r.title, "shows": r.shows, "seats_sold": r.seats_sold, "capacity": r.capacity,
            "occupancy_pct": occupancy(r.seats_sold, r.capacity), "takings_paise": r.takings_paise} for r in rows]
    return out[:FILM_CAP], len(out) > FILM_CAP


async def showtimes(conn: AsyncConnection, lo: datetime, hi: datetime, ids: tuple[int, ...] | None,
                    limit: int, offset: int) -> tuple[int, list]:
    """(total in the period and scope, one page ordered by starts_at then screen_id)."""
    scope = "" if ids is None else "AND st.screen_id = ANY(:screen_ids)"
    total = (await conn.execute(text(f"SELECT count(*) FROM showtime st WHERE st.starts_at >= :lo AND st.starts_at < :hi {scope}"),
                                _params(lo, hi, ids))).scalar_one()
    rows = (await conn.execute(text(f"""
        WITH s AS ({_per_show(ids)})
        SELECT s.*, sc.name AS screen_name, m.title
        FROM s JOIN screen sc ON sc.id = s.screen_id JOIN movie m ON m.id = s.movie_id
        ORDER BY s.starts_at ASC, s.screen_id ASC, s.id ASC
        LIMIT :limit OFFSET :offset"""), _params(lo, hi, ids, limit=limit, offset=offset))).all()
    if any(r.capacity is None or r.capacity <= 0 for r in rows):
        raise BadShowtime()
    return total, rows


async def screens(conn: AsyncConnection, ids: tuple[int, ...]) -> list[dict]:
    rows = (await conn.execute(text("SELECT id, name, is_active FROM screen WHERE id = ANY(:ids) ORDER BY id"),
                               {"ids": list(ids)})).all()
    return [{"screen_id": r.id, "screen_name": r.name, "is_active": r.is_active} for r in rows]


# ---- the change log (P-RPT-11): admin only, newest first, cursor on id -------------------------------------------------

async def audit(conn: AsyncConnection, lo: datetime, hi: datetime, filters: dict, cursor: int | None, limit: int) -> dict:
    """One page of audit rows plus the two option sets. The option sets read the DATE WINDOW ALONE - never the
    action / actor filters, never the page - so neither select can collapse or rewrite the other."""
    where, params = ["a.occurred_at >= :lo", "a.occurred_at < :hi"], {"lo": lo, "hi": hi}
    for column, value in filters.items():
        if value is not None:
            where.append(f"a.{column} = :{column}")
            params[column] = value
    if cursor is not None:
        where.append("a.id < :cursor")
        params["cursor"] = cursor
    rows = (await conn.execute(text(f"""
        SELECT a.id, a.occurred_at, a.actor_user_id, u.email AS actor_email, a.actor_role, a.action, a.entity_type,
               a.entity_id, a.before, a.after, a.request_id
        FROM audit_log a JOIN users u ON u.id = a.actor_user_id
        WHERE {' AND '.join(where)}
        ORDER BY a.id DESC LIMIT :limit"""), {**params, "limit": limit + 1})).all()
    window_only = {"lo": lo, "hi": hi}
    actions = (await conn.execute(text(
        "SELECT DISTINCT action FROM audit_log WHERE occurred_at >= :lo AND occurred_at < :hi ORDER BY action"),
        window_only)).scalars().all()
    actors = (await conn.execute(text("""
        SELECT DISTINCT a.actor_user_id, u.email AS actor_email FROM audit_log a JOIN users u ON u.id = a.actor_user_id
        WHERE a.occurred_at >= :lo AND a.occurred_at < :hi ORDER BY actor_email, a.actor_user_id"""), window_only)).all()
    page = rows[:limit]
    return {"rows": page, "next_cursor": page[-1].id if len(rows) > limit else None,
            "available_actions": list(actions),
            "available_actors": [{"actor_user_id": r.actor_user_id, "actor_email": r.actor_email} for r in actors]}

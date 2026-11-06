"""The reporting surface at /api/reports (E7): EP-RPT-01 dashboard, EP-RPT-02 showtimes, EP-RPT-03 scope, EP-RPT-04 audit.

READ ONLY: every route is a GET and nothing here writes (P-RPT-09). Any other method on these paths is answered 405
in the envelope by the one application-level handler (app/api/errors.py). No export of any kind (P-RPT-10).

AUTHORISATION ONCE, ON THE ROUTER (P-RPT-02). `router` carries the role dependency (manager or admin) and then
`report_scope`, which resolves the caller's halls from the session and applies any screen_id narrowing; the handlers
receive the resolved scope and never read a screen id themselves. `audit_router` admits the admin alone. Both spend
the caller's one reports bucket (app/api/deps.py), which fails closed on a Redis outage.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (ReportScope, db, get_clock, report_scope, reports_rate_limit, require_change_log,
                          require_reporting)
from app.api.errors import ApiError
from app.core.clock import Clock
from app.domain import reports as rpt
from app.domain.browse.catalogue import default_zone, load_zones, local_today

log = logging.getLogger("app.reports")

router = APIRouter(prefix="/api/reports", dependencies=[Depends(require_reporting), Depends(report_scope)])
audit_router = APIRouter(prefix="/api/reports", dependencies=[Depends(require_change_log), Depends(reports_rate_limit)])

FIGURES_FAILED = "This period's figures could not be loaded. If you need help, quote {request_id}."
SHOWS_FAILED = "This period's shows could not be loaded. If you need help, quote {request_id}."
LOG_FAILED = "The change log could not be loaded. If you need help, quote {request_id}."
BAD_LIMIT = "Ask for between 1 and 200 rows."
BAD_DATE = "The date must be written as YYYY-MM-DD."
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_INT = re.compile(r"-?\d{1,18}")


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(422, "VALIDATION_FAILED", message, {"field": field})


def _date(value: str, field: str) -> date:
    if not _DATE.fullmatch(value):
        raise _invalid(field, BAD_DATE)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _invalid(field, "That date does not exist.") from None


def _int(value: str | None, default: int, field: str, message: str, low: int, high: int | None = None) -> int:
    if value is None:
        return default
    number = int(value) if _INT.fullmatch(value) else None
    if number is None or number < low or (high is not None and number > high):
        raise _invalid(field, message)
    return number


async def _zone(conn: AsyncConnection) -> str:
    """The cinema ROW's zone (FR-ADR-018), never a constant and never the container's."""
    return default_zone(await load_zones(conn))


async def _period(conn: AsyncConnection, clock: Clock, period: str | None, date_text: str | None) -> dict:
    """P-RPT-01: validate, then resolve the local period and both UTC edges from the injected clock."""
    if period not in ("day", "week", "month"):
        raise _invalid("period", "Choose day, week or month.")
    anchor = _date(date_text, "date") if date_text is not None else None
    zone = await _zone(conn)
    await conn.rollback()
    now = clock.now()
    first, after = rpt.window(period, anchor or local_today(now, zone))
    return {"period": period, "zone": zone, "now": now, "lo": rpt.utc_midnight(first, zone), "hi": rpt.utc_midnight(after, zone)}


def _failed(message: str, where: str) -> ApiError:
    log.exception("report query failed", extra={"endpoint": where})
    return ApiError(500, "INTERNAL_ERROR", message)


@router.get("/dashboard")
async def dashboard(period: str | None = None, date: str | None = None, scope: ReportScope = Depends(report_scope),
                    conn: AsyncConnection = Depends(db), clock: Clock = Depends(get_clock)) -> dict:
    p = await _period(conn, clock, period, date)
    body = {"period": p["period"], "period_start_utc": rpt.utc_text(p["lo"]), "period_end_utc": rpt.utc_text(p["hi"]),
            "evaluated_at_utc": rpt.utc_text(p["now"]), "timezone": p["zone"], "scope_empty": scope.empty,
            "screen_ids": list(scope.screen_ids)}
    if scope.empty:
        # P-RPT-08: short-circuit. No aggregate runs, so no predicate is ever built from an empty list.
        return {**body, "takings_paise": 0, "seats_sold": 0, "capacity": 0, "occupancy_pct": None, "shows": 0,
                "films": [], "films_truncated": False}
    try:
        # P-RPT-07: the headline and the per-film rows read ONE snapshot, so the parts always sum to the whole.
        await conn.execution_options(isolation_level="REPEATABLE READ")
        async with conn.begin():
            figures = await rpt.headline(conn, p["lo"], p["hi"], scope.filter)
            films, truncated = await rpt.films(conn, p["lo"], p["hi"], scope.filter)
    except Exception:  # noqa: BLE001 - any failure means NO figure at all, never a partial body
        raise _failed(FIGURES_FAILED, "dashboard") from None
    return {**body, **figures, "films": films, "films_truncated": truncated}


@router.get("/showtimes")
async def showtimes(period: str | None = None, date: str | None = None, limit: str | None = None,
                    offset: str | None = None, scope: ReportScope = Depends(report_scope),
                    conn: AsyncConnection = Depends(db), clock: Clock = Depends(get_clock)) -> dict:
    p = await _period(conn, clock, period, date)
    size = _int(limit, 50, "limit", BAD_LIMIT, 1, 200)
    skip = _int(offset, 0, "offset", "The row offset cannot be negative.", 0)
    body = {"period_start_utc": rpt.utc_text(p["lo"]), "period_end_utc": rpt.utc_text(p["hi"]), "timezone": p["zone"],
            "limit": size, "offset": skip}
    if scope.empty:
        return {**body, "total": 0, "rows": []}
    try:
        total, rows = await rpt.showtimes(conn, p["lo"], p["hi"], scope.filter, size, skip)
    except Exception:  # noqa: BLE001
        raise _failed(SHOWS_FAILED, "showtimes") from None
    return {**body, "total": total, "rows": [{
        "showtime_id": r.id, "starts_at": rpt.local_text(r.starts_at, p["zone"]), "screen_id": r.screen_id,
        "screen_name": r.screen_name, "movie_id": r.movie_id, "title": r.title, "seats_sold": r.sold,
        "capacity": r.capacity, "occupancy_pct": rpt.occupancy(r.sold, r.capacity), "takings_paise": r.takings,
        # The application's injected clock decides this, never the database's (P-RPT-04).
        "has_started": p["now"] >= r.starts_at} for r in rows]}


@router.get("/scope")
async def reporting_scope(scope: ReportScope = Depends(report_scope), conn: AsyncConnection = Depends(db),
                 clock: Clock = Depends(get_clock)) -> dict:
    zone = await _zone(conn)
    screens = await rpt.screens(conn, scope.readable) if scope.readable else []
    return {"role": scope.caller_role, "scope_empty": not scope.readable, "all_halls": scope.all_halls, "screens": screens,
            "timezone": zone, "today": local_today(clock.now(), zone).isoformat()}


@audit_router.get("/audit")
async def audit(from_: str | None = Query(None, alias="from"), to: str | None = None, action: str | None = None,
                entity_type: str | None = None, entity_id: str | None = None, actor_user_id: str | None = None,
                limit: str | None = None, cursor: str | None = None,
                conn: AsyncConnection = Depends(db), clock: Clock = Depends(get_clock)) -> dict:
    """EP-RPT-04 (P-RPT-11). Reading the log is not itself audited."""
    zone = await _zone(conn)
    await conn.rollback()
    last = _date(to, "to") if to is not None else local_today(clock.now(), zone)
    first = _date(from_, "from") if from_ is not None else last - timedelta(days=30)
    if first > last:
        raise _invalid("from", "The start date must be on or before the end date.")
    size = _int(limit, 50, "limit", BAD_LIMIT, 1, 200)
    page = _int(cursor, 0, "cursor", "That page of results is no longer valid. Start again from the newest change.", 1)
    for field, value in (("action", action), ("entity_type", entity_type)):
        if value is not None and not 1 <= len(value) <= 64:
            raise _invalid(field, "Some fields need attention.")
    if entity_id is not None and entity_type is None:
        raise _invalid("entity_id", "Choose a record type before filtering by record id.")
    record = _int(entity_id, 0, "entity_id", "Some fields need attention.", 1)
    actor = _int(actor_user_id, 0, "actor_user_id", "Some fields need attention.", 1)
    lo, hi = rpt.utc_midnight(first, zone), rpt.utc_midnight(last + timedelta(days=1), zone)
    filters = {"action": action, "entity_type": entity_type, "entity_id": record or None, "actor_user_id": actor or None}
    try:
        found = await rpt.audit(conn, lo, hi, filters, page or None, size)
    except Exception:  # noqa: BLE001
        raise _failed(LOG_FAILED, "audit") from None
    rows = [{"id": r.id, "occurred_at": rpt.local_text(r.occurred_at, zone), "actor_user_id": r.actor_user_id,
             "actor_email": r.actor_email, "actor_role": r.actor_role, "action": r.action, "entity_type": r.entity_type,
             "entity_id": r.entity_id, "before": r.before, "after": r.after, "request_id": r.request_id}
            for r in found["rows"]]
    return {"window_start_utc": rpt.utc_text(lo), "window_end_utc": rpt.utc_text(hi), "timezone": zone, "rows": rows,
            "next_cursor": found["next_cursor"], "available_actions": found["available_actions"],
            "available_actors": found["available_actors"]}

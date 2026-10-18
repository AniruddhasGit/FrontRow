"""Halls and their seats (P-ADM-13 to P-ADM-16).

THE FREEZE (P-ADM-14) is decided here, never in a handler: once ANY showtime row exists on a screen -
past or future, booked or empty - a seat's row_label, seat_number and seat_category_id are frozen and a
seat cannot be deleted. Adding a seat, moving its grid position, taking it in or out of service and
renaming the hall stay permitted.

THE LOCK: every seat write takes SELECT ... FOR UPDATE on its screen row first, unconditionally, so a
seat added or retired in the same instant as a showtime creation is wholly inside that showtime's seat
set or wholly outside it (P-ADM-14).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.domain.admin.common import (audit, check_version, constraint_name, invalid, join_labels, need_bool,
                                     need_int, need_name, need_version, not_found, transaction, INT4_MAX)
from app.models import cinema, screen, seat, seat_category, showtime

HALL_GONE = "That hall no longer exists at this address."
SEAT_GONE = "That seat no longer exists at this address."
HALL_NAME = "Enter a hall name of 1 to 60 characters."
HALL_TAKEN = "A hall with that name already exists."
HALL_STALE = ("This hall was changed by someone else while you were editing. Reload to see the current details, "
              "then make your change again. Nothing you typed has been saved.")
ROW_LABEL = "Enter a row label of 1 to 4 letters, for example A or AA."
SEAT_NUMBER = "Enter a seat number of 1 or more."
GRID = "Enter a row and column position of 1 or more."
CATEGORY = "That seat category is not on the list. Choose one of the listed categories."
SEATS_BATCH = "Some fields need attention."

FROZEN_FIELDS = ["row_label", "seat_number", "seat_category_id"]
_LETTERS = re.compile(r"[A-Z]{1,4}")  # ASCII only (SRC-004 JC-R6-03); I is allowed (SRC-004 R-4)


class LayoutFrozen(ApiError):
    """409 LAYOUT_FROZEN for a frozen-field change or a delete on a hall that has showtimes."""

    def __init__(self, message: str, *, screen_id: int, seat_id: int, showtime_count: int) -> None:
        self.screen_id, self.seat_id, self.showtime_count = screen_id, seat_id, showtime_count
        super().__init__(409, "LAYOUT_FROZEN", message, {"screen_id": screen_id, "seat_id": seat_id,
                                                         "showtime_count": showtime_count,
                                                         "frozen_fields": list(FROZEN_FIELDS)})


# ---- reads -----------------------------------------------------------------------------------------------

def _count(table, *where):
    return select(func.count()).select_from(table).where(*where).scalar_subquery()


_HALL = (screen.c.id, screen.c.cinema_id, screen.c.name, screen.c.is_active,
         _count(seat, seat.c.screen_id == screen.c.id).label("seat_count_total"),
         _count(seat, seat.c.screen_id == screen.c.id, seat.c.is_active.is_(True)).label("seat_count_in_service"),
         (_count(showtime, showtime.c.screen_id == screen.c.id) > 0).label("has_showtimes"),
         screen.c.version)
_SEAT = (seat.c.id, seat.c.row_label, seat.c.seat_number, seat.c.grid_row, seat.c.grid_col, seat.c.seat_category_id,
         seat.c.is_active)


async def list_screens(conn: AsyncConnection) -> dict:
    rows = (await conn.execute(select(*_HALL).order_by(screen.c.name, screen.c.id))).mappings().all()
    return {"items": [dict(r) for r in rows]}


async def _hall(conn: AsyncConnection, screen_id: int) -> dict:
    return dict((await conn.execute(select(*_HALL).where(screen.c.id == screen_id))).mappings().one())


async def showtime_count(conn: AsyncConnection, screen_id: int) -> int:
    """The freeze's one question, evaluated inside the caller's transaction (P-ADM-13)."""
    return await conn.scalar(select(func.count()).select_from(showtime).where(showtime.c.screen_id == screen_id))


async def list_seats(conn: AsyncConnection, screen_id: int) -> dict:
    if await conn.scalar(select(screen.c.id).where(screen.c.id == screen_id)) is None:
        raise not_found(HALL_GONE)
    count = await showtime_count(conn, screen_id)
    rows = (await conn.execute(select(*_SEAT).where(seat.c.screen_id == screen_id)
                               .order_by(seat.c.grid_row, seat.c.grid_col, seat.c.id))).mappings().all()
    return {"has_showtimes": count > 0, "showtime_count": count, "items": [dict(r) for r in rows]}


async def lock_screen(conn: AsyncConnection, screen_id: int) -> dict | None:
    row = (await conn.execute(select(screen).where(screen.c.id == screen_id).with_for_update())).mappings().first()
    return dict(row) if row else None


# ---- halls -----------------------------------------------------------------------------------------------

async def _name_taken(conn: AsyncConnection, cinema_id: int, name: str, except_id: int | None = None) -> bool:
    q = select(func.count()).select_from(screen).where(screen.c.cinema_id == cinema_id,
                                                         func.lower(func.trim(screen.c.name)) == name.lower())
    if except_id is not None:
        q = q.where(screen.c.id != except_id)
    return bool(await conn.scalar(q))


def _hall_name_conflict(exc: IntegrityError) -> ApiError:
    if constraint_name(exc) == "uq_screen__name_ci":
        return invalid("name", HALL_TAKEN)
    raise exc


async def create_screen(conn: AsyncConnection, actor: Any, fields: dict, now: datetime) -> dict:
    # cinema_id is REQUIRED and never defaulted to the only row (P-ADM-25).
    cinema_id = need_int(fields.get("cinema_id"), "cinema_id")
    name = need_name(fields.get("name"), "name", 60, HALL_NAME)
    try:
        async with transaction(conn, (ACTION_SCREEN_CREATED,)):
            if await conn.scalar(select(cinema.c.id).where(cinema.c.id == cinema_id)) is None:
                raise invalid("cinema_id")
            if await _name_taken(conn, cinema_id, name):
                raise invalid("name", HALL_TAKEN)
            new_id = await conn.scalar(insert(screen).values(cinema_id=cinema_id, name=name, is_active=True, version=1)
                                       .returning(screen.c.id))
            await audit(conn, actor, ACTION_SCREEN_CREATED, "screen", new_id, None,
                        {"cinema_id": cinema_id, "name": name, "is_active": True}, now)
            return await _hall(conn, new_id)
    except IntegrityError as exc:
        raise _hall_name_conflict(exc) from None


# A module-level name, so a test can point it at a non-member and watch the boundary refuse it (S-ADM-02).
ACTION_SCREEN_CREATED = "screen.created"


async def edit_screen(conn: AsyncConnection, actor: Any, screen_id: int, fields: dict, now: datetime) -> dict:
    version = need_version(fields)
    try:
        async with transaction(conn, ("screen.updated", "screen.deactivated", "screen.reactivated")):
            row = await lock_screen(conn, screen_id)
            if row is None:
                raise not_found(HALL_GONE)
            check_version(row["version"], version, HALL_STALE)
            changes = {}
            if "name" in fields:
                changes["name"] = need_name(fields["name"], "name", 60, HALL_NAME)
            if "is_active" in fields:
                changes["is_active"] = need_bool(fields["is_active"], "is_active")
            changes = {k: v for k, v in changes.items() if v != row[k]}
            if changes:
                if "name" in changes and await _name_taken(conn, row["cinema_id"], changes["name"], screen_id):
                    raise invalid("name", HALL_TAKEN)
                await conn.execute(update(screen).where(screen.c.id == screen_id).values(**changes, version=row["version"] + 1))
                if "name" in changes:
                    await audit(conn, actor, "screen.updated", "screen", screen_id, {"name": row["name"]},
                                {"name": changes["name"]}, now)
                if "is_active" in changes:
                    action = "screen.reactivated" if changes["is_active"] else "screen.deactivated"
                    await audit(conn, actor, action, "screen", screen_id, {"is_active": row["is_active"]},
                                {"is_active": changes["is_active"]}, now)
            return await _hall(conn, screen_id)
    except IntegrityError as exc:
        raise _hall_name_conflict(exc) from None


# ---- seats -----------------------------------------------------------------------------------------------

def _row_label(value: Any) -> str:
    # Normalised to upper(trim(input)) before it is stored; the CHECK refuses anything else (SRC-004 R-4).
    # ASCII is checked BEFORE upper(): U+00DF upper-cases to "SS", and Python and PostgreSQL disagree on such letters.
    label = value.strip() if isinstance(value, str) and value.isascii() else ""
    label = label.upper()
    if not _LETTERS.fullmatch(label):
        raise invalid("row_label", ROW_LABEL)
    return label


def _seat_fields(raw: dict, *, partial: bool) -> dict:
    out = {}
    for name, check in (("row_label", _row_label),
                        ("seat_number", lambda v: need_int(v, "seat_number", maximum=INT4_MAX, wrong=SEAT_NUMBER)),
                        ("grid_row", lambda v: need_int(v, "grid_row", maximum=INT4_MAX, wrong=GRID)),
                        ("grid_col", lambda v: need_int(v, "grid_col", maximum=INT4_MAX, wrong=GRID)),
                        ("seat_category_id", lambda v: need_int(v, "seat_category_id", wrong=CATEGORY))):
        if name in raw:
            out[name] = check(raw[name])
        elif not partial:
            raise invalid(name, {"row_label": ROW_LABEL, "seat_number": SEAT_NUMBER, "seat_category_id": CATEGORY}.get(name, GRID))
    return out


def _labels_message(labels: list[str]) -> str:
    if len(labels) == 1:
        return f"Seat {labels[0]} already exists in this hall. Every seat in a hall needs its own row and number."
    return f"Seats {join_labels(labels)} already exist in this hall. Every seat in a hall needs its own row and number."


def _coords_message(count: int) -> str:
    if count == 1:
        return "Another seat is already drawn at that position in the map. Choose a different position."
    return f"Another seat is already drawn at {count} of those positions in the map. Choose different positions."


async def _categories_exist(conn: AsyncConnection, ids: set[int]) -> bool:
    found = await conn.scalar(select(func.count()).select_from(seat_category).where(seat_category.c.id.in_(ids)))
    return found == len(ids)


def _label(row: dict) -> str:
    return f"{row['row_label']}{row['seat_number']}"


async def add_seats(conn: AsyncConnection, actor: Any, screen_id: int, fields: dict, now: datetime) -> dict:
    """EP-ADM-19: 1..500 seats, all or nothing, permitted in BOTH hall states. One seat.created per seat."""
    batch = fields.get("seats")
    if not isinstance(batch, list) or not 1 <= len(batch) <= 500:
        raise invalid("seats", SEATS_BATCH)
    seats = []
    for i, raw in enumerate(batch):
        if not isinstance(raw, dict):
            raise invalid(f"seats.{i}", SEATS_BATCH)
        if set(raw) - {"row_label", "seat_number", "grid_row", "grid_col", "seat_category_id"}:
            raise ApiError(400, "REQUEST_INVALID")
        try:
            seats.append(_seat_fields(raw, partial=False))
        except ApiError as exc:
            exc.details = {**exc.details, "field": f"seats.{i}.{exc.details.get('field')}"}
            raise
    async with transaction(conn, ("seat.created",)):
        if await lock_screen(conn, screen_id) is None:
            raise not_found(HALL_GONE)
        if not await _categories_exist(conn, {s["seat_category_id"] for s in seats}):
            raise invalid("seat_category_id", CATEGORY)
        stored = (await conn.execute(select(seat.c.row_label, seat.c.seat_number, seat.c.grid_row, seat.c.grid_col)
                                     .where(seat.c.screen_id == screen_id))).all()
        taken_labels = {(r.row_label, r.seat_number) for r in stored}
        taken_cells = {(r.grid_row, r.grid_col) for r in stored}
        dup_labels, dup_cells = [], []
        for s in seats:  # in the order submitted (P-ADM-13); a repeat inside the batch is a collision too
            key, cell = (s["row_label"], s["seat_number"]), (s["grid_row"], s["grid_col"])
            if key in taken_labels:
                dup_labels.append(_label(s))
            if cell in taken_cells:
                dup_cells.append({"grid_row": cell[0], "grid_col": cell[1]})
            taken_labels.add(key)
            taken_cells.add(cell)
        if dup_labels:
            raise ApiError(422, "VALIDATION_FAILED", _labels_message(dup_labels), {"duplicate_labels": dup_labels})
        if dup_cells:
            raise ApiError(422, "VALIDATION_FAILED", _coords_message(len(dup_cells)), {"duplicate_coordinates": dup_cells})
        rows = (await conn.execute(insert(seat).returning(*_SEAT, sort_by_parameter_order=True),
                                   [{**s, "screen_id": screen_id, "is_active": True} for s in seats])).mappings().all()
        for r in rows:
            await audit(conn, actor, "seat.created", "seat", r["id"], None,
                        {k: r[k] for k in ("row_label", "seat_number", "grid_row", "grid_col", "seat_category_id", "is_active")}, now)
        return {"items": [dict(r) for r in rows]}


async def _locked_seat(conn: AsyncConnection, seat_id: int) -> tuple[dict, int]:
    """The seat, after its screen row is locked; and the showtime count read under that lock."""
    screen_id = await conn.scalar(select(seat.c.screen_id).where(seat.c.id == seat_id))
    if screen_id is None:
        raise not_found(SEAT_GONE)
    await lock_screen(conn, screen_id)
    row = (await conn.execute(select(seat).where(seat.c.id == seat_id).with_for_update())).mappings().first()
    if row is None:
        raise not_found(SEAT_GONE)
    return dict(row), await showtime_count(conn, screen_id)


async def edit_seat(conn: AsyncConnection, actor: Any, seat_id: int, fields: dict, now: datetime) -> dict:
    """EP-ADM-20. A seat carries no version. Setting is_active to the value it holds is 409, not a no-op
    (P-ADM-15 exception 3); every other unchanged field is an ordinary no-op (P-ADM-12)."""
    wanted = _seat_fields(fields, partial=True)
    if "is_active" in fields:
        wanted["is_active"] = need_bool(fields["is_active"], "is_active")
    async with transaction(conn, ("seat.updated", "seat.deactivated", "seat.reactivated")):
        row, count = await _locked_seat(conn, seat_id)
        changes = {k: v for k, v in wanted.items() if v != row[k]}
        frozen = [f for f in FROZEN_FIELDS if f in changes]
        if frozen and count > 0:
            if "row_label" in frozen or "seat_number" in frozen:
                message = (f"Seat {_label(row)} cannot be renumbered. This hall has showtimes, and a seat number is what "
                           "a past customer's ticket says. You can add a seat, or take a seat out of service.")
            else:
                message = (f"Seat {_label(row)} cannot be moved to a different category. This hall has showtimes, and its "
                           "seats are already priced. You can add a seat, or take a seat out of service.")
            raise LayoutFrozen(message, screen_id=row["screen_id"], seat_id=seat_id, showtime_count=count)
        if "is_active" in wanted and "is_active" not in changes:
            state = "in service" if row["is_active"] else "out of service"
            raise ApiError(409, "LAYOUT_FROZEN", f"Seat {_label(row)} is already {state}.",
                           {"screen_id": row["screen_id"], "seat_id": seat_id, "showtime_count": count,
                            "frozen_fields": list(FROZEN_FIELDS)})
        if "seat_category_id" in changes and not await _categories_exist(conn, {changes["seat_category_id"]}):
            raise invalid("seat_category_id", CATEGORY)
        merged = {**row, **changes}
        others = select(func.count()).select_from(seat).where(seat.c.screen_id == row["screen_id"], seat.c.id != seat_id)
        if {"row_label", "seat_number"} & set(changes) and await conn.scalar(
                others.where(seat.c.row_label == merged["row_label"], seat.c.seat_number == merged["seat_number"])):
            raise ApiError(422, "VALIDATION_FAILED", _labels_message([_label(merged)]), {"duplicate_labels": [_label(merged)]})
        if {"grid_row", "grid_col"} & set(changes) and await conn.scalar(
                others.where(seat.c.grid_row == merged["grid_row"], seat.c.grid_col == merged["grid_col"])):
            raise ApiError(422, "VALIDATION_FAILED", _coords_message(1),
                           {"duplicate_coordinates": [{"grid_row": merged["grid_row"], "grid_col": merged["grid_col"]}]})
        if changes:
            await conn.execute(update(seat).where(seat.c.id == seat_id).values(**changes))
            edited = {k: v for k, v in changes.items() if k != "is_active"}
            if edited:
                await audit(conn, actor, "seat.updated", "seat", seat_id, {k: row[k] for k in edited}, edited, now)
            if "is_active" in changes:
                action = "seat.reactivated" if changes["is_active"] else "seat.deactivated"
                await audit(conn, actor, action, "seat", seat_id, {"is_active": row["is_active"]},
                            {"is_active": changes["is_active"]}, now)
        return {k: merged[k] for k in ("id", "screen_id", "row_label", "seat_number", "grid_row", "grid_col",
                                       "seat_category_id", "is_active")}


async def delete_seat(conn: AsyncConnection, actor: Any, seat_id: int, now: datetime) -> None:
    """EP-ADM-21: one of the only two deletions (P-ADM-20), and only while the hall has no showtime row."""
    async with transaction(conn, ("seat.deleted",)):
        row, count = await _locked_seat(conn, seat_id)
        if count > 0:
            raise LayoutFrozen(f"Seat {_label(row)} cannot be removed. This hall has showtimes, and removing a seat would "
                               "break the record of who booked it. Take it out of service instead.",
                               screen_id=row["screen_id"], seat_id=seat_id, showtime_count=count)
        await conn.execute(delete(seat).where(seat.c.id == seat_id))
        await audit(conn, actor, "seat.deleted", "seat", seat_id,
                    {k: row[k] for k in ("screen_id", "row_label", "seat_number", "grid_row", "grid_col",
                                         "seat_category_id", "is_active")}, None, now)

"""The four lookup vocabularies a film is built from (P-ADM-23, P-ADM-24): list, create, withdraw, restore.

`kind` is matched against KINDS - a closed dict of table objects - and is never interpolated into SQL, so no caller-
supplied string ever names a table. A kind outside it is an address that does not exist: 404 "That page does not
exist.", the same body as an id that names nothing, so the response never reveals which ids exist.
There is no rename and no delete (FR-ADR-012): a typo is withdrawn and the right entry added, both on the record.
Uniqueness is lower(trim(name)) per vocabulary, withdrawn rows included, and the unique index is the guard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.domain.admin.common import audit, constraint_name, invalid, need_name, transaction, utc_text
from app.models import certification, format, genre, language, movie, movie_genre, showtime

KINDS = {"language": language, "certification": certification, "genre": genre, "format": format}
# What references each vocabulary: films for three of them, showtimes for format (EP-ADM-25). Every referencing
# row counts, visible or not - a draft holds an entry up exactly as much as a published film does.
_REFERENCED_BY = {"language": movie.c.language_id, "certification": movie.c.certification_id,
                  "genre": movie_genre.c.genre_id, "format": showtime.c.format_id}

NAME_BOUND = "Enter a name of 1 to 60 characters."
TAKEN = "That name is already on this list. Every entry needs its own name."
TAKEN_WITHDRAWN = ("That name is already on this list, on an entry that has been withdrawn. Restore that entry instead "
                   "of adding it again.")
IN_USE = "Choose whether this entry is in use."
ONLY_IN_USE = "That request could not be understood. This address changes only whether an entry is in use."


def table(kind: str):
    if kind not in KINDS:
        raise ApiError(404, "NOT_FOUND")  # the registry's "That page does not exist." (P-ADM-23 exception 3)
    return KINDS[kind]


def _out(row: Any) -> dict:
    return {"id": row.id, "name": row.name, "is_active": row.is_active, "created_at": utc_text(row.created_at)}


async def list_entries(conn: AsyncConnection, kind: str, include_withdrawn: bool) -> dict:
    t = table(kind)
    ref = _REFERENCED_BY[kind]
    uses = select(func.count()).select_from(ref.table).where(ref == t.c.id).scalar_subquery().label("reference_count")
    stmt = select(t.c.id, t.c.name, t.c.is_active, t.c.created_at, uses).order_by(t.c.name, t.c.id)
    if not include_withdrawn:
        stmt = stmt.where(t.c.is_active.is_(True))
    rows = (await conn.execute(stmt)).all()
    return {"kind": kind, "items": [{**_out(r), "reference_count": r.reference_count} for r in rows]}


async def _taken(conn: AsyncConnection, t, name: str) -> ApiError:
    active = await conn.scalar(select(t.c.is_active).where(func.lower(func.trim(t.c.name)) == name.lower()))
    return invalid("name", TAKEN_WITHDRAWN if active is False else TAKEN)


async def create_entry(conn: AsyncConnection, actor: Any, kind: str, fields: dict, now: datetime) -> dict:
    t = table(kind)
    name = need_name(fields.get("name"), "name", 60, NAME_BOUND)
    try:
        async with transaction(conn, (f"{kind}.created",)):
            if (await conn.scalar(select(func.count()).select_from(t)
                                  .where(func.lower(func.trim(t.c.name)) == name.lower()))):
                raise await _taken(conn, t, name)
            row = (await conn.execute(insert(t).values(name=name, is_active=True)
                                      .returning(t.c.id, t.c.name, t.c.is_active, t.c.created_at))).one()
            await audit(conn, actor, f"{kind}.created", kind, row.id, None, {"name": name}, now)
    except IntegrityError as exc:
        # Two identical creates in the same instant: the index decided, and the loser is told which remedy applies.
        if constraint_name(exc) == f"uq_{kind}__name_ci":
            raise await _taken(conn, t, name) from None
        raise
    return _out(row)


async def set_active(conn: AsyncConnection, actor: Any, kind: str, entry_id: int, fields: dict, now: datetime) -> dict:
    t = table(kind)
    if set(fields) - {"is_active"}:
        raise ApiError(400, "REQUEST_INVALID", ONLY_IN_USE, {"field": sorted(set(fields) - {"is_active"})[0]})
    wanted = fields.get("is_active")
    if type(wanted) is not bool:
        raise invalid("is_active", IN_USE)
    action = f"{kind}.{'restored' if wanted else 'withdrawn'}"
    async with transaction(conn, (action,)):
        row = (await conn.execute(select(t.c.id, t.c.name, t.c.is_active, t.c.created_at).where(t.c.id == entry_id)
                                  .with_for_update())).first()
        if row is None:
            raise ApiError(404, "NOT_FOUND")  # identical to an unknown kind (P-ADM-24 exception 2)
        if row.is_active == wanted:
            return _out(row)  # nothing written and no audit row (exception 4)
        row = (await conn.execute(update(t).where(t.c.id == entry_id).values(is_active=wanted, updated_at=now)
                                  .returning(t.c.id, t.c.name, t.c.is_active, t.c.created_at))).one()
        await audit(conn, actor, action, kind, entry_id, {"is_active": not wanted}, {"is_active": wanted}, now)
    return _out(row)

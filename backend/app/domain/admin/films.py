"""Films, authored by hand (P-ADM-01 to P-ADM-06): draft, edit, display window, poster key, publish, withdraw.

There is no other way a film enters this system: no external source, no import, no upsert, no schedule.
Every write: version (P-ADM-12) -> field validation -> the merged-row bound -> no-op -> write + audit, in ONE
transaction on a row re-read under FOR UPDATE, so the bound and the version are checked against the row as it is.
The two visibility gates are reported separately and computed by app/domain/visibility.py, never here.
display_from / display_until are naive local on the wire in both directions, in the cinema row's zone (E6 S4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, false, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.domain.admin.common import (INT4_MAX, audit, check_version, invalid, is_int, need_int, need_name, need_version,
                                     parse_local, to_local, to_utc, transaction, utc_text)
from app.domain.browse.catalogue import default_zone, load_zones
from app.domain.visibility import in_window, published, visible
from app.models import certification, genre, language, movie, movie_genre

TITLE = "Enter a title of 1 to 200 characters."
RUNTIME = "Enter the runtime in whole minutes, 1 or more."
SYNOPSIS = "The synopsis is longer than 4000 characters. Shorten it."
LANGUAGE = "That language is not on the list. Choose one of the listed languages."
CERTIFICATION = "That certification is not on the list. Choose one of the listed certifications."
GENRES = "Choose at least one genre from the list."
WINDOW_BAD = "Enter a date and a time for both the start and the end of the display window."
WINDOW_ORDER = "The display window must end after it starts."
GONE = "That film no longer exists at this address."
STALE = ("This film was changed by someone else while you were editing. Reload to see the current details, then make "
         "your change again. Nothing you typed has been saved.")
NO_POSTER = "This film has no poster. Upload a poster before publishing it."
NO_WINDOW = "This film has no display window. Set the dates it is shown between before publishing it."
ALREADY = "This film is already published."
NOT_PUBLISHED = "This film is not published, so there is nothing to withdraw."
BAD_FILTER = "That filter value is not valid."

AUTHORED = ("title", "synopsis", "runtime_minutes", "certification_id", "language_id", "genre_ids")
WINDOW = ("display_from", "display_until")


def _columns(now: datetime):
    return (movie, certification.c.name.label("certification_name"), language.c.name.label("language_name"),
            published().label("published"), func.coalesce(in_window(now), false()).label("window_open"),
            func.coalesce(visible(now), false()).label("is_visible_now"))


def _joined():
    return (movie.join(certification, movie.c.certification_id == certification.c.id)
            .join(language, movie.c.language_id == language.c.id))


async def _genres(conn: AsyncConnection, ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        rows = (await conn.execute(select(movie_genre.c.movie_id, genre.c.id, genre.c.name)
                                   .select_from(movie_genre.join(genre, movie_genre.c.genre_id == genre.c.id))
                                   .where(movie_genre.c.movie_id.in_(ids)).order_by(genre.c.name, genre.c.id))).all()
        for r in rows:
            out[r.movie_id].append({"id": r.id, "name": r.name})
    return out


def _local(instant: datetime | None, zone: str) -> str | None:
    return None if instant is None else to_local(instant, zone)


def _film(r: Any, genres: list[dict], zone: str) -> dict:
    return {"id": r.id, "title": r.title, "synopsis": r.synopsis, "runtime_minutes": r.runtime_minutes,
            "certification_id": r.certification_id, "language_id": r.language_id, "genre_ids": [g["id"] for g in genres],
            "certification": {"id": r.certification_id, "name": r.certification_name},
            "language": {"id": r.language_id, "name": r.language_name}, "genres": genres,
            "poster_present": r.poster_object_key is not None,
            # Whole seconds on the wire (EP-ADM-01's instant shape); the stored instant and the audit row keep it exactly.
            "published_at": None if r.published_at is None else utc_text(r.published_at.replace(microsecond=0)),
            "display_from": _local(r.display_from, zone), "display_until": _local(r.display_until, zone),
            "published": r.published, "window_open": r.window_open, "is_visible_now": r.is_visible_now,
            "version": r.version, "created_at": utc_text(r.created_at)}


async def _zone(conn: AsyncConnection) -> str:
    # The cinema row's zone is the only authority (P-ADM-26); one cinema in v1 (SRC-003 C-2).
    return default_zone(await load_zones(conn))


async def get_film(conn: AsyncConnection, movie_id: int, now: datetime) -> dict:
    row = (await conn.execute(select(*_columns(now)).select_from(_joined()).where(movie.c.id == movie_id))).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", GONE)
    return _film(row, (await _genres(conn, [row.id]))[row.id], await _zone(conn))


def _page(value: str | None, field: str, default: int, low: int, high: int | None) -> int:
    if value is None:
        return default
    if not value.isdigit() or int(value) < low or (high is not None and int(value) > high):
        raise invalid(field, BAD_FILTER)
    return int(value)


async def list_films(conn: AsyncConnection, now: datetime, status: str | None, limit: str | None, offset: str | None) -> dict:
    """EP-ADM-01. created_at DESC, id DESC: a total order, so paging never shows one film twice."""
    if status not in (None, "all", "draft", "published"):
        raise invalid("status", BAD_FILTER)
    size, skip = _page(limit, "limit", 50, 1, 100), _page(offset, "offset", 0, 0, None)
    where = {"draft": ~published(), "published": published()}.get(status)
    count = select(func.count()).select_from(movie)
    stmt = select(*_columns(now)).select_from(_joined())
    if where is not None:
        count, stmt = count.where(where), stmt.where(where)
    rows = (await conn.execute(stmt.order_by(movie.c.created_at.desc(), movie.c.id.desc()).limit(size).offset(skip))).all()
    genres, zone = await _genres(conn, [r.id for r in rows]), await _zone(conn)
    return {"items": [_film(r, genres[r.id], zone) for r in rows], "total": await conn.scalar(count)}


# ---- field rules (P-ADM-01's validation table, applied unchanged on the edit) ---------------------------------------


async def _lookup_ok(conn: AsyncConnection, t, value: Any, keep: set[int]) -> bool:
    """Exists, and offered: a withdrawn entry cannot be given to a film anew (P-ADM-24), but a film already carrying it
    keeps it (`keep`)."""
    if not is_int(value):
        return False
    active = await conn.scalar(select(t.c.is_active).where(t.c.id == value))
    return active is True or (active is False and value in keep)


async def _validate(conn: AsyncConnection, fields: dict, stored: dict | None) -> dict:
    """The submitted authored fields, validated and normalised. `stored` is the current row on an edit, else None."""
    out: dict[str, Any] = {}
    if "title" in fields:
        out["title"] = need_name(fields["title"], "title", 200, TITLE)
    if "synopsis" in fields:
        if not isinstance(fields["synopsis"], str) or len(fields["synopsis"]) > 4000:
            raise invalid("synopsis", SYNOPSIS)
        out["synopsis"] = fields["synopsis"]
    if "runtime_minutes" in fields:
        out["runtime_minutes"] = need_int(fields["runtime_minutes"], "runtime_minutes", maximum=INT4_MAX, wrong=RUNTIME)
    for key, t, message in (("language_id", language, LANGUAGE), ("certification_id", certification, CERTIFICATION)):
        if key in fields:
            if not await _lookup_ok(conn, t, fields[key], {stored[key]} if stored else set()):
                raise invalid(key, message)
            out[key] = fields[key]
    if "genre_ids" in fields:
        ids, kept = fields["genre_ids"], set(stored["genre_ids"]) if stored else set()
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 10 or not all(is_int(i) for i in ids)
                or len(set(ids)) != len(ids)):
            raise invalid("genre_ids", GENRES)
        rows = (await conn.execute(select(genre.c.id, genre.c.is_active).where(genre.c.id.in_(ids)))).all()
        offered = {r.id for r in rows if r.is_active or r.id in kept}
        if offered != set(ids):
            raise invalid("genre_ids", GENRES)
        out["genre_ids"] = sorted(ids)
    return out


async def create_film(conn: AsyncConnection, actor: Any, fields: dict, now: datetime) -> dict:
    for key in AUTHORED:
        if key not in fields:
            raise invalid(key, {"title": TITLE, "runtime_minutes": RUNTIME, "genre_ids": GENRES, "language_id": LANGUAGE,
                                "certification_id": CERTIFICATION}.get(key))
    async with transaction(conn, ("movie.created",)):
        values = await _validate(conn, fields, None)
        genre_ids = values.pop("genre_ids")
        movie_id = await conn.scalar(insert(movie).values(**values, version=1, created_at=now).returning(movie.c.id))
        await conn.execute(insert(movie_genre), [{"movie_id": movie_id, "genre_id": g} for g in genre_ids])
        await audit(conn, actor, "movie.created", "movie", movie_id, None, {**values, "genre_ids": genre_ids}, now)
    return await get_film(conn, movie_id, now)


async def _lock(conn: AsyncConnection, movie_id: int) -> dict:
    row = (await conn.execute(select(movie).where(movie.c.id == movie_id).with_for_update())).mappings().first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", GONE)
    return dict(row)


def _window_text(row: dict) -> dict:
    return {k: None if row[k] is None else utc_text(row[k]) for k in WINDOW}


async def edit_film(conn: AsyncConnection, actor: Any, movie_id: int, fields: dict, now: datetime) -> dict:
    version = need_version(fields)
    async with transaction(conn, ("movie.updated", "movie.display_window_changed")):
        row = await _lock(conn, movie_id)
        check_version(row["version"], version, STALE)
        row["genre_ids"] = sorted((await conn.execute(select(movie_genre.c.genre_id)
                                                      .where(movie_genre.c.movie_id == movie_id))).scalars().all())
        values = await _validate(conn, fields, row)
        zone = await _zone(conn)
        for key in WINDOW:
            if key in fields:
                values[key] = to_utc(parse_local(fields[key], key, WINDOW_BAD), zone)
        merged = {**row, **values}
        # The bound is on the PAIR in the merged row, never on the fields this request happened to carry (E6 S4).
        if merged["display_from"] is not None and merged["display_until"] is not None \
                and merged["display_until"] <= merged["display_from"]:
            raise invalid("display_until", WINDOW_ORDER)
        changed = {k: v for k, v in values.items() if v != row[k]}
        if not changed:
            return await get_film(conn, movie_id, now)  # a no-op: nothing written, version unchanged (P-ADM-12)
        if "genre_ids" in changed:
            # The join rows ARE the field: replacing the set is the edit. DELETE is granted on movie_genre and on no
            # other film table (datamodel.json grants); no film, booking or audit row is removed.
            await conn.execute(delete(movie_genre).where(movie_genre.c.movie_id == movie_id))
            await conn.execute(insert(movie_genre), [{"movie_id": movie_id, "genre_id": g} for g in changed["genre_ids"]])
        await conn.execute(update(movie).where(movie.c.id == movie_id).values(
            **{k: v for k, v in changed.items() if k != "genre_ids"}, version=row["version"] + 1))
        authored = [k for k in AUTHORED if k in changed]
        if authored:
            await audit(conn, actor, "movie.updated", "movie", movie_id, {k: row[k] for k in authored},
                        {k: changed[k] for k in authored}, now)
        if any(k in changed for k in WINDOW):
            await audit(conn, actor, "movie.display_window_changed", "movie", movie_id, _window_text(row),
                        _window_text(merged), now)
    return await get_film(conn, movie_id, now)


async def publish(conn: AsyncConnection, actor: Any, movie_id: int, fields: dict, now: datetime) -> dict:
    version = need_version(fields)
    async with transaction(conn, ("movie.published",)):
        # Both preconditions are read HERE, under the lock - never from the form or an earlier read (P-ADM-05).
        row = await _lock(conn, movie_id)
        check_version(row["version"], version, STALE)
        if row["published_at"] is not None:
            raise ApiError(409, "PUBLISH_BLOCKED", ALREADY)
        if row["poster_object_key"] is None:
            raise ApiError(409, "PUBLISH_BLOCKED", NO_POSTER, {"field": "poster"})
        if row["display_from"] is None or row["display_until"] is None:
            raise ApiError(409, "PUBLISH_BLOCKED", NO_WINDOW, {"field": "display_from"})
        await conn.execute(update(movie).where(movie.c.id == movie_id).values(published_at=now, version=row["version"] + 1))
        await audit(conn, actor, "movie.published", "movie", movie_id, {"published_at": None},
                    {"published_at": utc_text(now)}, now)
    return await get_film(conn, movie_id, now)


async def unpublish(conn: AsyncConnection, actor: Any, movie_id: int, fields: dict, now: datetime) -> dict:
    """Withdrawal, not deletion: the row, its showtimes and every booking stay exactly as they are (P-ADM-06)."""
    version = need_version(fields)
    async with transaction(conn, ("movie.unpublished",)):
        row = await _lock(conn, movie_id)
        check_version(row["version"], version, STALE)
        if row["published_at"] is None:
            raise ApiError(409, "PUBLISH_BLOCKED", NOT_PUBLISHED)
        await conn.execute(update(movie).where(movie.c.id == movie_id).values(published_at=None, version=row["version"] + 1))
        await audit(conn, actor, "movie.unpublished", "movie", movie_id, {"published_at": utc_text(row["published_at"])},
                    {"published_at": None}, now)
    return await get_film(conn, movie_id, now)


# ---- the poster's row half (the bytes are app/domain/posters.py's) --------------------------------------------------


async def poster_row(conn: AsyncConnection, movie_id: int) -> dict:
    """The cheap read before any byte reaches S3: version and current key, no lock (P-ADM-03 step 4)."""
    row = (await conn.execute(select(movie.c.version, movie.c.poster_object_key).where(movie.c.id == movie_id))).first()
    await conn.rollback()  # end the implicit read transaction; the write opens its own
    if row is None:
        raise ApiError(404, "NOT_FOUND", GONE)
    return {"version": row.version, "poster_object_key": row.poster_object_key}


async def attach_poster(conn: AsyncConnection, actor: Any, movie_id: int, version: int, key: str, now: datetime) -> dict:
    """P-ADM-03 step 9: re-read under the lock, compare version AGAIN, point the film at the new object."""
    async with transaction(conn, ("movie.poster_uploaded", "movie.poster_replaced")):
        row = await _lock(conn, movie_id)
        check_version(row["version"], version, STALE)
        previous = row["poster_object_key"]
        await conn.execute(update(movie).where(movie.c.id == movie_id).values(poster_object_key=key, version=row["version"] + 1))
        if previous is None:
            await audit(conn, actor, "movie.poster_uploaded", "movie", movie_id, None, {"poster_object_key": key}, now)
        else:
            await audit(conn, actor, "movie.poster_replaced", "movie", movie_id, {"poster_object_key": previous},
                        {"poster_object_key": key}, now)
    return await get_film(conn, movie_id, now)

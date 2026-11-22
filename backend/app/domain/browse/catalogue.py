"""The public read path's queries: the listing, one film, a film's showtimes, one showtime, the vocabularies
(P-BRW-01..07, EP-BRW-01/02/04/05/07).

VISIBILITY (P-BRW-01) is ONE predicate, `visible(t)`, applied in SQL on every movie-addressed query - never a
filter in Python after the fetch, which is the one a later refactor drops. Published (IS NOT NULL - a record of
when, never compared to the clock) AND display_from <= T < display_until. A null on either window side fails
the comparison, so no COALESCE and no special case. The showtime header and the seat map apply no movie gate
today; whether they should is OPEN-BRWVIS-01, reserved, and nothing here answers it.

TIME (FR-ADR-018). T is the injected clock's instant. A local calendar date becomes an instant range in the
cinema row's zone, read from the database and never from a literal. Every instant leaves in its cinema's offset,
never as Z, so the client formats and performs no zone arithmetic.

THE SALES CUT-OFF (P-BRW-07, PROVISIONAL "after"). sales_close_at = starts_at + SALES_CUTOFF_MINUTES, derived
at read time, never stored. Open is strictly T < sales_close_at; in SQL that is starts_at > T - cutoff.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import BigInteger, and_, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

# THE visibility predicate (P-BRW-01, P-ADM-05) lives in one module; every movie-addressed query here applies it.
from app.domain.visibility import visible
from app.models import (certification, cinema, format, genre, language, movie, movie_genre, movie_like, movie_rating, review_vote,
                        screen, showtime, users)


class SortOption(str, enum.Enum):
    """The listing's sort vocabulary (P-BRW-03). One member while no other sort is ruled (OPEN-SORT-01)."""

    NEWEST = "newest"


@dataclass(frozen=True)
class ListingFilters:
    date: date | None = None
    language_id: int | None = None
    format_id: int | None = None
    cinema_id: int | None = None


@dataclass(frozen=True)
class ShowtimeFilters:
    cinema_id: int | None = None
    format_id: int | None = None


async def load_zones(conn: AsyncConnection) -> dict[int, str]:
    """{cinema_id: IANA zone name}, from the cinema rows (one row in v1, SRC-003 C-2)."""
    return {r.id: r.timezone for r in (await conn.execute(select(cinema.c.id, cinema.c.timezone).order_by(cinema.c.id))).all()}


def default_zone(zones: dict[int, str], cinema_id: int | None = None) -> str:
    """The zone "today" and a film's own instants are read in: the chosen cinema's, else the first cinema's - always
    a cinema ROW's zone (P-ADM-26). [JUDGMENT CALL] With one cinema (v1) every choice is the same one. With no
    cinema row at all there is no showtime and nothing to show, and UTC only keeps the arithmetic defined."""
    if cinema_id in zones:
        return zones[cinema_id]
    return next(iter(zones.values()), "UTC")


def local_iso(instant: datetime, zone: str) -> str:
    return instant.astimezone(ZoneInfo(zone)).isoformat()


def local_today(now: datetime, zone: str) -> date:
    return now.astimezone(ZoneInfo(zone)).date()


def _midnight(day: date, zone: str) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(zone))


def on_local_days(zones: dict[int, str], first: date, until: date | None):
    """showtime.starts_at within [first, until) as LOCAL days of the showtime's cinema. Needs `screen` joined.
    One zone (v1) compiles to exactly `starts_at >= :lo AND starts_at < :hi`; several zones OR one range each."""
    by_zone: dict[str, list[int]] = {}
    for cinema_id, zone in zones.items():
        by_zone.setdefault(zone, []).append(cinema_id)
    if not by_zone:
        return false()
    ranges = []
    for zone, ids in by_zone.items():
        bound = [showtime.c.starts_at >= _midnight(first, zone)]
        if until is not None:
            bound.append(showtime.c.starts_at < _midnight(until, zone))
        ranges.append(and_(*bound) if len(by_zone) == 1 else and_(screen.c.cinema_id.in_(ids), *bound))
    return ranges[0] if len(ranges) == 1 else or_(*ranges)


def listing_statement(t: datetime, f: ListingFilters, zones: dict[int, str]):
    """EP-BRW-01. The film matches language_id, and ONE showtime matches every supplied showtime filter at once:
    a single EXISTS, never one per filter (P-BRW-04)."""
    stmt = (select(movie.c.id, movie.c.title, movie.c.synopsis, movie.c.runtime_minutes, movie.c.display_until,
                   movie.c.release_date, movie.c.cast_members, movie.c.crew_members,
                   certification.c.id.label("certification_id"), certification.c.name.label("certification_name"),
                   language.c.id.label("language_id"), language.c.name.label("language_name"))
            .select_from(movie.join(certification, movie.c.certification_id == certification.c.id)
                         .join(language, movie.c.language_id == language.c.id))
            .where(visible(t)))
    if f.language_id is not None:
        stmt = stmt.where(movie.c.language_id == f.language_id)
    one_showtime = []
    if f.date is not None:
        scoped = {k: v for k, v in zones.items() if f.cinema_id is None or k == f.cinema_id}
        one_showtime.append(on_local_days(scoped, f.date, f.date + timedelta(days=1)))
    if f.cinema_id is not None:
        one_showtime.append(screen.c.cinema_id == f.cinema_id)
    if f.format_id is not None:
        one_showtime.append(showtime.c.format_id == f.format_id)
    if one_showtime:
        stmt = stmt.where(exists(select(showtime.c.id).select_from(showtime.join(screen, showtime.c.screen_id == screen.c.id))
                                 .where(showtime.c.movie_id == movie.c.id, *one_showtime)))
    return stmt.order_by(movie.c.published_at.desc(), movie.c.id.desc())


async def _genres(conn: AsyncConnection, movie_ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {m: [] for m in movie_ids}
    if movie_ids:
        rows = (await conn.execute(select(movie_genre.c.movie_id, genre.c.id, genre.c.name)
                                   .select_from(movie_genre.join(genre, movie_genre.c.genre_id == genre.c.id))
                                   .where(movie_genre.c.movie_id.in_(movie_ids))
                                   .order_by(movie_genre.c.movie_id, genre.c.name, genre.c.id))).all()
        for r in rows:
            out[r.movie_id].append({"id": r.id, "name": r.name})
    return out


def coming_soon(release_date: date | None, t: datetime, zone: str) -> bool:
    """CR-008 T10/T12: released after the cinema's today. No release date counts as released (it is optional)."""
    return release_date is not None and release_date > local_today(t, zone)


def average_tenths(total: int, n: int) -> int | None:
    """The mean score x10, half up, in integers (no float on the wire): scores 7 and 8 -> 75."""
    return None if n == 0 else (20 * total + n) // (2 * n)


async def _ratings(conn: AsyncConnection, movie_ids: list[int]) -> dict[int, dict]:
    """CR-008 T12: {movie_id: {rating: {average_tenths, count}, likes}}, aggregated on each listing build (the listing
    cache holds the result; a rating or like write bumps the listing generation)."""
    out = {m: {"rating": {"average_tenths": None, "count": 0}, "likes": 0} for m in movie_ids}
    if movie_ids:
        for m, n, total in (await conn.execute(
                select(movie_rating.c.movie_id, func.count(), func.sum(movie_rating.c.score).cast(BigInteger))
                .where(movie_rating.c.movie_id.in_(movie_ids)).group_by(movie_rating.c.movie_id))).all():
            out[m]["rating"] = {"average_tenths": average_tenths(total, n), "count": n}
        for m, n in (await conn.execute(select(movie_like.c.movie_id, func.count())
                                         .where(movie_like.c.movie_id.in_(movie_ids), movie_like.c.liked)
                                         .group_by(movie_like.c.movie_id))).all():
            out[m]["likes"] = n
    return out


async def rating_breakdown(conn: AsyncConnection, movie_id: int) -> dict:
    """The film page's rating block: average, count, and how many gave each score 1..10 (CR-008 T12)."""
    counts = dict((await conn.execute(select(movie_rating.c.score, func.count()).where(movie_rating.c.movie_id == movie_id)
                                      .group_by(movie_rating.c.score))).all())
    n, total = sum(counts.values()), sum(s * c for s, c in counts.items())
    return {"average_tenths": average_tenths(total, n), "count": n, "breakdown": [counts.get(s, 0) for s in range(1, 11)]}


def people(text: str | None) -> list[dict]:
    """cast_members / crew_members: one person per line, 'Name: role' (the role is optional)."""
    out = []
    for line in (text or "").splitlines():
        name, _, role = line.partition(":")
        if name.strip():
            out.append({"name": name.strip(), "role": role.strip() or None})
    return out


def _film(row: Any, genres: list[dict], zone: str, t: datetime, stats: dict) -> dict:
    return {"id": row.id, "title": row.title, "synopsis": row.synopsis, "runtime_minutes": row.runtime_minutes,
            "certification": {"id": row.certification_id, "name": row.certification_name},
            "language": {"id": row.language_id, "name": row.language_name},
            "genres": genres, "poster_url": f"/api/movies/{row.id}/poster", "display_until": local_iso(row.display_until, zone),
            # CR-008 T10-T12: the release date, Coming soon, the star average and the like count, on every card
            "release_date": row.release_date.isoformat() if row.release_date else None,
            "coming_soon": coming_soon(row.release_date, t, zone), **stats}


async def list_movies(conn: AsyncConnection, t: datetime, f: ListingFilters, zones: dict[int, str], zone: str) -> dict:
    rows = (await conn.execute(listing_statement(t, f, zones))).all()
    ids = [r.id for r in rows]
    genres, stats = await _genres(conn, ids), await _ratings(conn, ids)
    films = [_film(r, genres[r.id], zone, t, stats[r.id]) for r in rows]
    return {"count": len(films), "movies": films}


async def get_movie(conn: AsyncConnection, t: datetime, movie_id: int, zone: str) -> dict | None:
    """EP-BRW-02. None for a film failing a gate AND for one that never existed: one answer, so a draft id
    cannot be told from a missing one. CR-008 T12: plus the full details (cast, crew) and the 1-10 breakdown."""
    row = (await conn.execute(listing_statement(t, ListingFilters(), {}).where(movie.c.id == movie_id))).first()
    if row is None:
        return None
    film = _film(row, (await _genres(conn, [row.id]))[row.id], zone, t, (await _ratings(conn, [row.id]))[row.id])
    return {**film, "rating": await rating_breakdown(conn, row.id), "cast": people(row.cast_members),
            "crew": people(row.crew_members)}


REVIEW_LIMIT = 50
REVIEW_SORTS = ("newest", "helpful")
REVIEWER = "FrontRow viewer"  # a reviewer who set no display name; the email is never shown


async def reviews(conn: AsyncConnection, t: datetime, movie_id: int, sort: str, zone: str) -> dict | None:
    """CR-011 F4: a visible film's reviews - ratings that carry text, all by verified viewers (the write's gate) - newest
    first or most helpful first (ties newest), at most REVIEW_LIMIT, with the total. None when the film is not visible."""
    if (await conn.execute(select(movie.c.id).where(movie.c.id == movie_id, visible(t)))).first() is None:
        return None
    helpful = (select(func.count()).select_from(review_vote).where(review_vote.c.rating_id == movie_rating.c.id)
               .scalar_subquery())
    written = func.coalesce(movie_rating.c.updated_at, movie_rating.c.created_at)
    order = [written.desc(), movie_rating.c.id.desc()]
    if sort == "helpful":
        order = [helpful.desc(), *order]
    where = (movie_rating.c.movie_id == movie_id, movie_rating.c.review_text.is_not(None))
    total = (await conn.execute(select(func.count()).select_from(movie_rating).where(*where))).scalar()
    rows = (await conn.execute(select(movie_rating.c.id, movie_rating.c.score, movie_rating.c.review_text, written.label("at"),
                                      users.c.display_name, helpful.label("helpful"))
                               .select_from(movie_rating.join(users, movie_rating.c.user_id == users.c.id))
                               .where(*where).order_by(*order).limit(REVIEW_LIMIT))).all()
    return {"movie_id": movie_id, "count": total, "items": [
        {"id": r.id, "author": (r.display_name or "").strip() or REVIEWER, "score": r.score, "text": r.review_text,
         "written_at": local_iso(r.at, zone), "helpful": r.helpful} for r in rows]}


SEARCH_LIMIT = 8


def _like_pattern(words: str) -> str:
    """LIKE's own wildcards in the typed text are escaped, so '%' finds a literal percent sign."""
    return "%" + words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def search(conn: AsyncConnection, t: datetime, q: str) -> dict:
    """CR-008 T9: visible films whose title, or one of whose genres, contains `q` (case-insensitive); title matches
    first, then by title; at most SEARCH_LIMIT. Fewer than 2 characters finds nothing (every film has an 'e')."""
    words = " ".join(q.split())
    if len(words) < 2:
        return {"items": []}
    pattern = _like_pattern(words)
    by_title = movie.c.title.ilike(pattern, escape="\\")
    by_genre = exists(select(movie_genre.c.movie_id).select_from(movie_genre.join(genre, movie_genre.c.genre_id == genre.c.id))
                      .where(movie_genre.c.movie_id == movie.c.id, genre.c.name.ilike(pattern, escape="\\")))
    rows = (await conn.execute(select(movie.c.id, movie.c.title, by_title.label("by_title"))
                               .where(visible(t), or_(by_title, by_genre))
                               .order_by(by_title.desc(), movie.c.title, movie.c.id).limit(SEARCH_LIMIT))).all()
    genres = await _genres(conn, [r.id for r in rows])
    return {"items": [{"id": r.id, "title": r.title, "genres": genres[r.id], "poster_url": f"/api/movies/{r.id}/poster",
                       "matched": "title" if r.by_title else "genre"} for r in rows]}


def _sales(starts_at: datetime, now: datetime, cutoff: timedelta, zone: str) -> dict:
    close = starts_at + cutoff
    return {"sales_close_at": local_iso(close, zone), "sales_closed": not (now < close)}


def next_date_statement(film: dict, day: date, f: ShowtimeFilters, now: datetime, cutoff: timedelta, zones: dict[int, str]):
    """next_date_with_showtimes' one showtime (P-BRW-06): strictly after `day`, inside the film's display window
    (bounded above by display_until itself - the search never runs past it), still open at `now`, and matching
    every filter this request carried. All four on ONE row; the earliest wins."""
    scoped = {k: v for k, v in zones.items() if f.cinema_id is None or k == f.cinema_id}
    first = max(day + timedelta(days=1), local_today(film["display_from"], default_zone(scoped)))
    where = [showtime.c.movie_id == film["id"], on_local_days(scoped, first, None),
             showtime.c.starts_at < film["display_until"], showtime.c.starts_at > now - cutoff]
    if f.cinema_id is not None:
        where.append(screen.c.cinema_id == f.cinema_id)
    if f.format_id is not None:
        where.append(showtime.c.format_id == f.format_id)
    return (select(showtime.c.starts_at, cinema.c.timezone)
            .select_from(showtime.join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id))
            .where(*where).order_by(showtime.c.starts_at, showtime.c.id).limit(1))


async def list_showtimes(conn: AsyncConnection, now: datetime, cutoff: timedelta, movie_id: int, day: date | None,
                         f: ShowtimeFilters, zones: dict[int, str]) -> dict | None:
    """EP-BRW-04. None when the film fails a gate (the caller answers 404). A closed showtime is listed and
    marked, never dropped (P-BRW-07)."""
    film = (await conn.execute(select(movie.c.id, movie.c.display_from, movie.c.display_until)
                               .where(movie.c.id == movie_id, visible(now)))).mappings().first()
    if film is None:
        return None
    day = day or local_today(now, default_zone(zones, f.cinema_id))
    scoped = {k: v for k, v in zones.items() if f.cinema_id is None or k == f.cinema_id}
    where = [showtime.c.movie_id == movie_id, on_local_days(scoped, day, day + timedelta(days=1))]
    if f.cinema_id is not None:
        where.append(screen.c.cinema_id == f.cinema_id)
    if f.format_id is not None:
        where.append(showtime.c.format_id == f.format_id)
    rows = (await conn.execute(
        select(showtime.c.id, showtime.c.starts_at, showtime.c.ends_at, showtime.c.base_price_paise,
               screen.c.id.label("screen_id"), screen.c.name.label("screen_name"),
               cinema.c.id.label("cinema_id"), cinema.c.name.label("cinema_name"), cinema.c.timezone,
               format.c.id.label("format_id"), format.c.name.label("format_name"))
        .select_from(showtime.join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id)
                     .outerjoin(format, showtime.c.format_id == format.c.id))
        .where(*where).order_by(showtime.c.starts_at, showtime.c.id))).all()
    nxt = (await conn.execute(next_date_statement(dict(film), day, f, now, cutoff, zones))).first()
    return {
        "date": day.isoformat(),
        "next_date_with_showtimes": nxt.starts_at.astimezone(ZoneInfo(nxt.timezone)).date().isoformat() if nxt else None,
        "showtimes": [{
            "id": r.id, "starts_at": local_iso(r.starts_at, r.timezone), "ends_at": local_iso(r.ends_at, r.timezone),
            **_sales(r.starts_at, now, cutoff, r.timezone),
            "screen": {"id": r.screen_id, "name": r.screen_name}, "cinema": {"id": r.cinema_id, "name": r.cinema_name},
            "format": {"id": r.format_id, "name": r.format_name} if r.format_id is not None else None,
            "base_price_paise": r.base_price_paise,
        } for r in rows],
    }


async def get_showtime(conn: AsyncConnection, now: datetime, cutoff: timedelta, showtime_id: int) -> dict | None:
    """EP-BRW-05: the seat-map screen's header. No movie gate (OPEN-BRWVIS-01 is reserved and unanswered)."""
    r = (await conn.execute(
        select(showtime.c.id, showtime.c.starts_at, showtime.c.ends_at, showtime.c.base_price_paise,
               movie.c.id.label("movie_id"), movie.c.title, movie.c.runtime_minutes,
               certification.c.id.label("certification_id"), certification.c.name.label("certification_name"),
               screen.c.id.label("screen_id"), screen.c.name.label("screen_name"),
               cinema.c.id.label("cinema_id"), cinema.c.name.label("cinema_name"), cinema.c.timezone)
        .select_from(showtime.join(movie, showtime.c.movie_id == movie.c.id)
                     .join(certification, movie.c.certification_id == certification.c.id)
                     .join(screen, showtime.c.screen_id == screen.c.id).join(cinema, screen.c.cinema_id == cinema.c.id))
        .where(showtime.c.id == showtime_id))).first()
    if r is None:
        return None
    return {"id": r.id,
            "movie": {"id": r.movie_id, "title": r.title, "certification": {"id": r.certification_id, "name": r.certification_name},
                      "runtime_minutes": r.runtime_minutes},
            "screen": {"id": r.screen_id, "name": r.screen_name}, "cinema": {"id": r.cinema_id, "name": r.cinema_name},
            "starts_at": local_iso(r.starts_at, r.timezone), "ends_at": local_iso(r.ends_at, r.timezone),
            **_sales(r.starts_at, now, cutoff, r.timezone), "base_price_paise": r.base_price_paise}


async def reference(conn: AsyncConnection, now: datetime, cutoff: timedelta) -> dict:
    """EP-BRW-07: the rows IN USE - referenced by something a caller can see now (P-BRW-04). is_active is
    deliberately not a filter: a withdrawn row a visible film still carries is returned (P-ADM-24)."""

    async def rows(table, joined, *where) -> list[dict]:
        stmt = (select(table.c.id, table.c.name).distinct().select_from(joined).where(*where)
                .order_by(table.c.name, table.c.id))
        return [{"id": r.id, "name": r.name} for r in (await conn.execute(stmt)).all()]

    open_showtimes = showtime.join(movie, showtime.c.movie_id == movie.c.id)
    still_open = showtime.c.starts_at > now - cutoff
    return {
        "cinemas": await rows(cinema, open_showtimes.join(screen, showtime.c.screen_id == screen.c.id)
                              .join(cinema, screen.c.cinema_id == cinema.c.id), visible(now), still_open),
        "languages": await rows(language, movie.join(language, movie.c.language_id == language.c.id), visible(now)),
        "formats": await rows(format, open_showtimes.join(format, showtime.c.format_id == format.c.id), visible(now), still_open),
        "certifications": await rows(certification, movie.join(certification, movie.c.certification_id == certification.c.id),
                                     visible(now)),
    }

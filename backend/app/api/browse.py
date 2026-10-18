"""PUBLIC router at /api: movies, showtimes, the seat map, reference data (EP-BRW-01, 02, 04, 05, 06, 07).
No session dependency - a guest browses. GET only: Lax cookies ride on cross-site GETs (P-XCT-06).

No route here carries ANY dependency (S-BRW-07): settings, the clock, Redis and the engine come from app.state,
and a handler opens its own connection AFTER its parameters validate, so a 422 runs no SQL at all.

Not mounted: GET /api/movies/{movie_id}/poster (EP-BRW-03). A presigned S3 URL needs the AWS SDK's credential
chain (the ECS task role), and the SDK arrives with Phase 5 (SRC-004 JC-R6-04). poster_url still names that
path, and the client draws the perforation motif when the image does not load (P-BRW-02 exception 1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response
from redis.exceptions import RedisError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core import cache
from app.core.ratelimit import Bucket, client_ip, enforce
from app.domain.browse import catalogue, seatmap
from app.domain.money import BIGINT_MAX

router = APIRouter(prefix="/api")
log = logging.getLogger("app.browse")

# The sentences this epic owns (E1 S4/S5). The server says them; the client renders what it is given.
MOVIE_NOT_SHOWING = "That movie is not showing."
SHOWTIME_NOT_FOUND = "That showtime could not be found."
BAD_DATE = "That date is not valid."
BAD_FILTER = "That filter is not valid."
BAD_SORT = "That sort option is not available."
SITE_DOWN = "The site is temporarily unavailable. Please try again in a moment."
SEATMAP_DOWN = "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes."

# EP-BRW-06's limit (FR-ADR-058): per IP, RATE_LIMIT_SEATMAP_IP_PER_MIN per 60 s. No per-user bucket - the route
# is public and there is no user to key one on. It runs BEFORE the cache and fails closed (P-BRW-12, X-7).
SEATMAP_IP = Bucket("seatmap-ip", "RATE_LIMIT_SEATMAP_IP_PER_MIN", 60, "Too many requests. Try again in {span}.")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_POSITIVE = re.compile(r"^[1-9]\d{0,18}$")
# A positive bigint id in the path; anything else is 422 before the handler runs.
Id = Annotated[int, Path(gt=0, le=BIGINT_MAX)]


def _date(value: str | None) -> date | None:
    """YYYY-MM-DD, strictly: a datetime, an offset or 2026-8-15 is refused, never coerced (P-BRW-04)."""
    if value is None:
        return None
    try:
        if _ISO_DATE.match(value):
            return date.fromisoformat(value)
    except ValueError:
        pass
    raise ApiError(422, "VALIDATION_FAILED", BAD_DATE, {"field": "date"})


def _id(value: str | None, field: str, message: str | None = BAD_FILTER) -> int | None:
    if value is None:
        return None
    if _POSITIVE.match(value) and int(value) <= BIGINT_MAX:
        return int(value)
    raise ApiError(422, "VALIDATION_FAILED", message, {"field": field})


@asynccontextmanager
async def _db(request: Request) -> AsyncIterator[AsyncConnection]:
    """One pooled connection; PostgreSQL unreachable is 503 with the epic's own sentence (P-BRW-01 row 5)."""
    try:
        async with request.app.state.db_engine.connect() as conn:
            yield conn
    except (OperationalError, InterfaceError, OSError) as exc:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", SITE_DOWN) from exc
    except DBAPIError as exc:
        if exc.connection_invalidated:
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", SITE_DOWN) from exc
        raise


def _json(body: object) -> bytes:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


def _fingerprint(endpoint: str, **params: object) -> str:
    """The listings cache key's filter component: every parameter that can change the body, resolved."""
    canonical = json.dumps({"endpoint": endpoint, **params}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _cutoff(request: Request) -> timedelta:
    return timedelta(minutes=request.app.state.settings.SALES_CUTOFF_MINUTES)


@router.get("/movies")
async def list_movies(request: Request, date: str | None = Query(None), language_id: str | None = Query(None),
                      format_id: str | None = Query(None), cinema_id: str | None = Query(None),
                      sort: str | None = Query(None)) -> Response:
    """EP-BRW-01. An absent date means every date: no predicate, no default to today (P-BRW-04)."""
    try:
        catalogue.SortOption(sort or catalogue.SortOption.NEWEST.value)
    except ValueError:
        raise ApiError(422, "VALIDATION_FAILED", BAD_SORT, {"field": "sort"}) from None
    filters = catalogue.ListingFilters(date=_date(date), language_id=_id(language_id, "language_id"),
                                       format_id=_id(format_id, "format_id"), cinema_id=_id(cinema_id, "cinema_id"))
    state = request.app.state
    now = state.clock.now()

    async def build() -> bytes:
        async with _db(request) as conn:
            zones = await catalogue.load_zones(conn)
            zone = catalogue.default_zone(zones, filters.cinema_id)
            return _json(await catalogue.list_movies(conn, now, filters, zones, zone))

    body = await cache.listing(state.redis, state.settings, _fingerprint("movies", **vars(filters)), build)
    return Response(body, media_type="application/json")


@router.get("/movies/{movie_id}")
async def get_movie(request: Request, movie_id: Id) -> Response:
    """EP-BRW-02. A film failing a gate and one that never existed get the SAME 404 (P-BRW-01 rows 3 and 4)."""
    state = request.app.state
    async with _db(request) as conn:
        zones = await catalogue.load_zones(conn)
        film = await catalogue.get_movie(conn, state.clock.now(), movie_id, catalogue.default_zone(zones))
    if film is None:
        raise ApiError(404, "NOT_FOUND", MOVIE_NOT_SHOWING)
    return Response(_json(film), media_type="application/json")


@router.get("/showtimes")
async def list_showtimes(request: Request, movie_id: str | None = Query(None), date: str | None = Query(None),
                         cinema_id: str | None = Query(None), format_id: str | None = Query(None)) -> Response:
    """EP-BRW-04. An absent date is today in the cinema's zone from the injected clock (P-BRW-06)."""
    film_id = _id(movie_id or "", "movie_id", None)
    day = _date(date)
    filters = catalogue.ShowtimeFilters(cinema_id=_id(cinema_id, "cinema_id"), format_id=_id(format_id, "format_id"))
    state = request.app.state
    now = state.clock.now()

    async def build() -> bytes:
        async with _db(request) as conn:
            zones = await catalogue.load_zones(conn)
            listed = await catalogue.list_showtimes(conn, now, _cutoff(request), film_id, day, filters, zones)
        if listed is None:
            raise ApiError(404, "NOT_FOUND", MOVIE_NOT_SHOWING)  # raised, so a 404 is never cached
        return _json(listed)

    if day is None:
        # Not cached: "today" is the cinema's local date, which only the database's zone can resolve, and a key
        # built from any other date would serve one local day's list on another (P-BRW-06's worked example).
        body = await build()
    else:
        body = await cache.listing(state.redis, state.settings,
                                   _fingerprint("showtimes", movie_id=film_id, date=day, **vars(filters)), build)
    return Response(body, media_type="application/json")


@router.get("/showtimes/{showtime_id}")
async def get_showtime(request: Request, showtime_id: Id) -> Response:
    """EP-BRW-05: the seat-map screen's header. No movie gate (OPEN-BRWVIS-01)."""
    async with _db(request) as conn:
        found = await catalogue.get_showtime(conn, request.app.state.clock.now(), _cutoff(request), showtime_id)
    if found is None:
        raise ApiError(404, "NOT_FOUND", SHOWTIME_NOT_FOUND)
    return Response(_json(found), media_type="application/json")


@router.get("/showtimes/{showtime_id}/seatmap")
async def get_seatmap(request: Request, showtime_id: Id) -> Response:
    """EP-BRW-06. Rate limit, then cache, then PostgreSQL + the seat locks. Identical for every caller."""
    state = request.app.state
    await enforce(request, [(SEATMAP_IP, client_ip(request, state.settings))], SEATMAP_DOWN)
    now = state.clock.now()

    async def build() -> bytes:
        async with _db(request) as conn:
            loaded = await seatmap.load_seatmap(conn, showtime_id)
        if loaded is None:
            raise ApiError(404, "NOT_FOUND", SHOWTIME_NOT_FOUND)
        head, seats = loaded
        held: set[int] = set()
        if seats:
            values = await state.redis.mget([cache.seat_lock_key(showtime_id, s.id) for s in seats])
            held = {s.id for s, v in zip(seats, values) if v is not None}
        try:
            built = seatmap.assemble(head, seats, held, now, _cutoff(request), state.settings.SEATMAP_POLL_INTERVAL_SECONDS)
        except seatmap.SeatMapFault:
            log.error("seat map fault", exc_info=True, extra={"showtime_id": showtime_id})
            raise ApiError(500, "INTERNAL_ERROR") from None
        return built.model_dump_json().encode()

    try:
        body = await cache.seatmap(state.redis, state.settings, showtime_id, build)
    except (RedisError, OSError):
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", SEATMAP_DOWN) from None
    # no-store: the client polls this every few seconds and a browser-cached copy would freeze the map.
    return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})


@router.get("/reference")
async def get_reference(request: Request) -> Response:
    """EP-BRW-07: the vocabularies in use. Uncached: four small DISTINCT queries, and a stale vocabulary would
    offer a filter value whose only result is an empty list."""
    async with _db(request) as conn:
        body = await catalogue.reference(conn, request.app.state.clock.now(), _cutoff(request))
    return Response(_json(body), media_type="application/json")

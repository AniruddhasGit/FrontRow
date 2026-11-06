"""EP-ADM-01..08: films. No DELETE is mounted on a film: "delete a film" is unpublish (P-ADM-06), and a DELETE here
answers 405 from the global handler. A write that can change a customer listing bumps the listing generation after it
commits (P-BRW-12), so the first GET /api/movies after the 200 already reads the new state."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, current_user, db, get_clock, get_settings
from app.api.errors import ApiError
from app.core import cache
from app.domain import posters
from app.domain.admin import films
from app.domain.admin.common import BIGINT_MAX, STALE_FORM, AdminBody, check_version, invalid, submitted

router = APIRouter()
MovieId = Path(gt=0, le=BIGINT_MAX)

NO_LENGTH = "The upload did not declare its size and was not accepted. Try again."
TOO_LARGE = "That file is larger than 2 MB. Choose a smaller image."
ONE_FILE = "Choose exactly one image file."
POSTER_DB_DOWN = ("The system cannot reach its database right now. The poster was not saved against this film. Try again "
                  "in a moment.")


class FilmCreate(AdminBody):
    title: Any = None
    synopsis: Any = None
    runtime_minutes: Any = None
    certification_id: Any = None
    language_id: Any = None
    genre_ids: Any = None


class FilmPatch(FilmCreate):
    version: Any = None
    display_from: Any = None
    display_until: Any = None


class VersionOnly(AdminBody):
    version: Any = None


class Named(BaseModel):
    id: int
    name: str


class Film(BaseModel):
    """The editor's film. Two gates, two booleans - `published` and `window_open` - and no combined flag named
    live or visible (S-ADM-27); is_visible_now is EP-ADM-01/03's read-only conjunction of the two."""

    id: int
    title: str
    synopsis: str
    runtime_minutes: int
    certification_id: int
    language_id: int
    genre_ids: list[int]
    certification: Named
    language: Named
    genres: list[Named]
    poster_present: bool
    published_at: str | None
    display_from: str | None
    display_until: str | None
    published: bool
    window_open: bool
    is_visible_now: bool
    version: int
    created_at: str


class FilmPage(BaseModel):
    items: list[Film]
    total: int


@router.get("/movies", response_model=FilmPage)
async def list_films(status: str | None = Query(None), limit: str | None = Query(None), offset: str | None = Query(None),
                     conn=Depends(db), clock=Depends(get_clock)):
    return await films.list_films(conn, clock.now(), status, limit, offset)


@router.post("/movies", status_code=201, response_model=Film)
async def create_film(body: FilmCreate, conn=Depends(db), user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await films.create_film(conn, user, submitted(body), clock.now())


@router.get("/movies/{movie_id}", response_model=Film)
async def get_film(movie_id: int = MovieId, conn=Depends(db), clock=Depends(get_clock)):
    return await films.get_film(conn, movie_id, clock.now())


@router.patch("/movies/{movie_id}", response_model=Film)
async def edit_film(request: Request, body: FilmPatch, movie_id: int = MovieId, conn=Depends(db),
                    user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    film = await films.edit_film(conn, user, movie_id, submitted(body), clock.now())
    await cache.bump_listing_generation(request.app.state.redis)
    return film


@router.post("/movies/{movie_id}/publish", response_model=Film)
async def publish(request: Request, body: VersionOnly, movie_id: int = MovieId, conn=Depends(db),
                  user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    film = await films.publish(conn, user, movie_id, submitted(body), clock.now())
    await cache.bump_listing_generation(request.app.state.redis)
    return film


@router.post("/movies/{movie_id}/unpublish", response_model=Film)
async def unpublish(request: Request, body: VersionOnly, movie_id: int = MovieId, conn=Depends(db),
                    user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    film = await films.unpublish(conn, user, movie_id, submitted(body), clock.now())
    await cache.bump_listing_generation(request.app.state.redis)
    return film


def _parts(content_type: str, body: bytes) -> list:
    """multipart/form-data, parsed by the standard library (no multipart package is installed, SRC-002 §13.1)."""
    if not content_type.lower().startswith("multipart/form-data"):
        return []
    message = BytesParser(policy=policy.HTTP).parsebytes(b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    return list(message.iter_parts()) if message.is_multipart() else []


@router.post("/movies/{movie_id}/poster", status_code=201, response_model=Film)
async def upload_poster(request: Request, movie_id: int = MovieId, conn=Depends(db), user: CurrentUser = Depends(current_user),
                        clock=Depends(get_clock), settings=Depends(get_settings)):
    """P-ADM-03's order: Content-Length (at the header, before a byte is read) -> version -> declared type and magic
    bytes -> decode and dimensions -> PutObject -> the row and its audit row in one transaction. No body parameter is
    declared, so the framework reads nothing before the header checks below have passed."""
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        raise ApiError(422, "VALIDATION_FAILED", NO_LENGTH, {"field": "Content-Length"})
    if int(length) > settings.POSTER_MAX_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", TOO_LARGE)
    stored = await films.poster_row(conn, movie_id)
    # Bounded by the check above: at most POSTER_MAX_BYTES held, in memory only - nothing reaches the disk.
    parts = _parts(request.headers.get("content-type", ""), await request.body())
    files = [p for p in parts if p.get_filename() is not None]
    fields = [p for p in parts if p.get_filename() is None]
    unknown = sorted({p.get_param("name", header="content-disposition") or "" for p in fields} - {"version"})
    if unknown:
        raise ApiError(400, "REQUEST_INVALID", details={"field": unknown[0]})
    versions = [p.get_payload(decode=True).decode("latin-1").strip() for p in fields]
    if len(versions) != 1 or not versions[0].isdigit():
        raise invalid("version", STALE_FORM)  # a header or a query parameter is not where it goes (P-ADM-03)
    version = int(versions[0])
    check_version(stored["version"], version, films.STALE)  # the cheap refusal: a stale upload costs no object
    if len(files) != 1:
        raise invalid("file", ONE_FILE)
    declared, data = files[0].get_content_type(), files[0].get_payload(decode=True)
    posters.check_image(declared, data)
    key = posters.new_key(movie_id)  # never the client's filename
    await posters.store(request.app.state).put(key, data, declared)
    try:
        return await films.attach_poster(conn, user, movie_id, version, key, clock.now())
    except ApiError as exc:
        if exc.status == 503:  # the bytes reached S3 but the row did not (exception 13); the object stays unreferenced
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", POSTER_DB_DOWN) from exc
        raise


@router.get("/movies/{movie_id}/poster")
async def poster(request: Request, movie_id: int = MovieId, conn=Depends(db)):
    """302 to a presigned GET, minted now, valid PRESIGNED_URL_TTL_SECONDS. A draft's poster is reachable only here."""
    key = (await films.poster_row(conn, movie_id))["poster_object_key"]
    if key is None:
        raise ApiError(404, "NOT_FOUND")
    return RedirectResponse(posters.store(request.app.state).presign(key), status_code=302)

"""The customer's own account surface (CR-008 T3-T7): summary, rewards, bookmarks, notifications, profile.

Same rule as app/api/me.py, and the same dependency: /api/me/ means the caller, resolved from the session once on the
router (me.caller). No handler takes a user id from the path, query or body, and every statement filters on the
caller's id in its own WHERE - another account's notification id or bookmark simply matches no row.

Nothing here is polled. The header reads /api/me/summary on navigation, as Shell.tsx reads /api/auth/me (CR-008 T7).
"""

from __future__ import annotations

import re

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import db
from app.api.errors import ApiError
from app.api.me import UNAVAILABLE, _bounded, _down, caller
from app.core import cache
from app.domain import rewards
from app.domain.browse import catalogue
from app.domain.money import BIGINT_MAX
from app.domain.visibility import visible
from app.models import bookmark, format as format_t, language, movie, movie_like, movie_rating, review_vote, users

router = APIRouter(prefix="/api/me", dependencies=[Depends(caller)])

Id = Annotated[int, Field(gt=0, le=BIGINT_MAX)]
NO_FILM = "That film could not be found."
BAD_BODY = "This request could not be processed."


def _bad() -> ApiError:
    return ApiError(400, "REQUEST_INVALID", BAD_BODY)


async def _json(request: Request, model: type[BaseModel]) -> BaseModel:
    """Parsed here so an unknown property or a wrong type is one 400 (no field echoed), as the confirm does."""
    try:
        return model.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise _bad() from None


async def _guard(work):
    """Postgres unreachable is 503, never a 500 (the /api/me pattern)."""
    try:
        return await work
    except Exception as exc:
        if _down(exc):
            raise ApiError(503, "DEPENDENCY_UNAVAILABLE", UNAVAILABLE) from None
        raise


# ---- T5/T7: the sidebar's one read ----------------------------------------------------------------------------------


@router.get("/summary")
async def my_summary(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    return await _guard(rewards.summary(conn, request.state.caller.id))


# ---- T3: rewards --------------------------------------------------------------------------------------------------


@router.get("/rewards")
async def my_rewards(request: Request, quote_paise: str | None = None, conn: AsyncConnection = Depends(db)) -> dict:
    """Balance, rules, history; with ?quote_paise=<order total> also what "use my points" would do to it (the checkout's
    preview - the confirm recomputes it against the server's hold and refuses a different total)."""
    quote = None if quote_paise is None else _bounded(quote_paise, 0, BIGINT_MAX, "That is not a valid amount.", "quote_paise")
    settings = request.app.state.settings
    return await _guard(rewards.history(conn, request.state.caller.id, settings.CURRENCY_MINOR_UNIT_RATIO, quote))


# ---- T4: bookmarks ------------------------------------------------------------------------------------------------


class Saved(BaseModel):
    model_config = ConfigDict(extra="forbid")
    saved: StrictBool


@router.get("/bookmarks")
async def my_bookmarks(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    """The wishlist: saved films a customer can currently see, newest bookmark first. A saved film that has left the
    listing stays saved and reappears when it is visible again."""
    async def read():
        rows = (await conn.execute(select(movie.c.id, movie.c.title, movie.c.runtime_minutes)
                                   .select_from(bookmark.join(movie, bookmark.c.movie_id == movie.c.id))
                                   .where(bookmark.c.user_id == request.state.caller.id, bookmark.c.saved,
                                          visible(request.app.state.clock.now()))
                                   .order_by(bookmark.c.updated_at.desc(), bookmark.c.id.desc()))).all()
        await conn.rollback()
        return {"items": [{"movie_id": r.id, "title": r.title, "runtime_minutes": r.runtime_minutes,
                           "poster_url": f"/api/movies/{r.id}/poster"} for r in rows]}

    return await _guard(read())


@router.put("/bookmarks/{movie_id}")
async def set_bookmark(request: Request, movie_id: Id, conn: AsyncConnection = Depends(db)) -> dict:
    """Save or un-save one film. One upsert on UNIQUE(user_id, movie_id): a double click never makes two rows, and
    un-saving is an UPDATE (frontrow_app has no DELETE on bookmark). Idempotent: the same body twice is the same state."""
    body = await _json(request, Saved)
    now = request.app.state.clock.now()

    async def write():
        async with conn.begin():
            if (await conn.execute(select(movie.c.id).where(movie.c.id == movie_id, visible(now)))).first() is None:
                raise ApiError(404, "NOT_FOUND", NO_FILM)
            await conn.execute(pg_insert(bookmark).values(user_id=request.state.caller.id, movie_id=movie_id, saved=body.saved,
                                                          created_at=now, updated_at=now)
                               .on_conflict_do_update(index_elements=["user_id", "movie_id"],
                                                      set_={"saved": body.saved, "updated_at": now}))
        return {"movie_id": movie_id, "saved": body.saved}

    return await _guard(write())


# ---- T12: ratings and likes ---------------------------------------------------------------------------------------
# A rating is for a released film: any signed-in customer, no booking needed (CR-013, owner 2026-11-23; checked in the
# write's own transaction, never from the client). One row per caller and film, re-rating updates it. A like is for a
# film that is not out yet (release_date after the cinema's today). Both bump the listing generation, so every card's average
# and like count is fresh on the next read. A re-rate pulls created_at back to now if it lay ahead (a demo account's
# future-dated rating, scripts/demo_reviews.py), so the writer's own rating always shows at once.

RATE_REFUSED = "Ratings open once the film is out. Until then, like it."
LIKE_REFUSED = "Likes are for films that are not out yet. Once it is out, see it and rate it."
BAD_SCORE = "Choose a score from 1 to 10."


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: StrictInt


class Liked(BaseModel):
    model_config = ConfigDict(extra="forbid")
    liked: StrictBool


async def _visible_film(conn: AsyncConnection, movie_id: int, now) -> bool:
    """Whether the film is coming soon, or 404 - the bookmark's gate, plus the release date read in the cinema's zone."""
    row = (await conn.execute(select(movie.c.release_date).where(movie.c.id == movie_id, visible(now)))).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", NO_FILM)
    return catalogue.coming_soon(row.release_date, now, catalogue.default_zone(await catalogue.load_zones(conn)))


@router.get("/movies/{movie_id}")
async def my_film(request: Request, movie_id: Id, conn: AsyncConnection = Depends(db)) -> dict:
    """The film page's per-viewer half: my score, whether I may rate, whether I liked it."""
    me, now = request.state.caller.id, request.app.state.clock.now()

    async def read():
        soon = await _visible_film(conn, movie_id, now)
        score = (await conn.execute(select(movie_rating.c.score).where(movie_rating.c.user_id == me,
                                                                      movie_rating.c.movie_id == movie_id))).scalar()
        liked = (await conn.execute(select(movie_like.c.liked).where(movie_like.c.user_id == me,
                                                                    movie_like.c.movie_id == movie_id))).scalar()
        # CR-011 F4: my review's text, and which of this film's reviews I have already marked Helpful
        review = (await conn.execute(select(movie_rating.c.id, movie_rating.c.review_text)
                                     .where(movie_rating.c.user_id == me, movie_rating.c.movie_id == movie_id))).first()
        voted = (await conn.execute(select(review_vote.c.rating_id)
                                    .select_from(review_vote.join(movie_rating, review_vote.c.rating_id == movie_rating.c.id))
                                    .where(review_vote.c.user_id == me, movie_rating.c.movie_id == movie_id)
                                    .order_by(review_vote.c.rating_id))).scalars().all()
        await conn.rollback()
        return {"movie_id": movie_id, "score": score, "can_rate": not soon, "liked": bool(liked), "coming_soon": soon,
                "review": review.review_text if review else None,
                "review_id": review.id if review and review.review_text else None, "voted": list(voted)}

    return await _guard(read())


@router.put("/ratings/{movie_id}")
async def rate_film(request: Request, movie_id: Id, conn: AsyncConnection = Depends(db)) -> dict:
    body = await _json(request, Score)
    if not 1 <= body.score <= 10:
        raise ApiError(422, "VALIDATION_FAILED", BAD_SCORE, {"field": "score"})
    me, now = request.state.caller.id, request.app.state.clock.now()

    async def write():
        async with conn.begin():
            if await _visible_film(conn, movie_id, now):
                raise ApiError(403, "FORBIDDEN", RATE_REFUSED)
            await conn.execute(pg_insert(movie_rating).values(user_id=me, movie_id=movie_id, score=body.score,
                                                              created_at=now, updated_at=now)
                               .on_conflict_do_update(index_elements=["user_id", "movie_id"],
                                                      set_={"score": body.score, "updated_at": now,
                                                            "created_at": func.least(movie_rating.c.created_at, now)}))
            rating = await catalogue.rating_breakdown(conn, movie_id, now)
        await cache.bump_listing_generation(request.app.state.redis)
        return {"movie_id": movie_id, "score": body.score, "rating": rating}

    return await _guard(write())


@router.put("/likes/{movie_id}")
async def like_film(request: Request, movie_id: Id, conn: AsyncConnection = Depends(db)) -> dict:
    body = await _json(request, Liked)
    me, now = request.state.caller.id, request.app.state.clock.now()

    async def write():
        async with conn.begin():
            soon = await _visible_film(conn, movie_id, now)
            if not soon:
                raise ApiError(403, "FORBIDDEN", LIKE_REFUSED)
            await conn.execute(pg_insert(movie_like).values(user_id=me, movie_id=movie_id, liked=body.liked,
                                                            created_at=now, updated_at=now)
                               .on_conflict_do_update(index_elements=["user_id", "movie_id"],
                                                      set_={"liked": body.liked, "updated_at": now}))
            likes = (await conn.execute(select(func.count()).select_from(movie_like)
                                        .where(movie_like.c.movie_id == movie_id, movie_like.c.liked))).scalar()
        await cache.bump_listing_generation(request.app.state.redis)
        return {"movie_id": movie_id, "liked": body.liked, "likes": likes}

    return await _guard(write())


# ---- CR-011 F4: reviews and Helpful votes ---------------------------------------------------------------------------
# A review is the caller's rating with text: written and edited under the rating's own gate (a released film, in the
# write's transaction; CR-013). A Helpful vote is once per customer per review (UNIQUE + on_conflict_do_nothing,
# so a second press changes nothing), never on the caller's own review, and never undone (insert-only table).

REVIEW_BOUNDS = "Write a review of 1 to 2000 characters."
NO_REVIEW = "That review could not be found."
OWN_REVIEW = "You cannot mark your own review as helpful."
REVIEW_MAX = 2000


class Written(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: StrictInt
    text: StrictStr


@router.put("/reviews/{movie_id}")
async def review_film(request: Request, movie_id: Id, conn: AsyncConnection = Depends(db)) -> dict:
    body = await _json(request, Written)
    text = body.text.strip()
    if not 1 <= body.score <= 10:
        raise ApiError(422, "VALIDATION_FAILED", BAD_SCORE, {"field": "score"})
    if not 1 <= len(text) <= REVIEW_MAX:
        raise ApiError(422, "VALIDATION_FAILED", REVIEW_BOUNDS, {"field": "text"})
    me, now = request.state.caller.id, request.app.state.clock.now()

    async def write():
        async with conn.begin():
            if await _visible_film(conn, movie_id, now):
                raise ApiError(403, "FORBIDDEN", RATE_REFUSED)
            review_id = (await conn.execute(
                pg_insert(movie_rating).values(user_id=me, movie_id=movie_id, score=body.score, review_text=text,
                                               created_at=now, updated_at=now)
                .on_conflict_do_update(index_elements=["user_id", "movie_id"],
                                       set_={"score": body.score, "review_text": text, "updated_at": now,
                                             "created_at": func.least(movie_rating.c.created_at, now)})
                .returning(movie_rating.c.id))).scalar()
            rating = await catalogue.rating_breakdown(conn, movie_id, now)
        await cache.bump_listing_generation(request.app.state.redis)
        return {"movie_id": movie_id, "review_id": review_id, "score": body.score, "text": text, "rating": rating}

    return await _guard(write())


@router.post("/reviews/{review_id}/helpful")
async def mark_helpful(request: Request, review_id: Id, conn: AsyncConnection = Depends(db)) -> dict:
    me, now = request.state.caller.id, request.app.state.clock.now()

    async def write():
        async with conn.begin():
            author = (await conn.execute(select(movie_rating.c.user_id)
                                         .select_from(movie_rating.join(movie, movie_rating.c.movie_id == movie.c.id))
                                         .where(movie_rating.c.id == review_id, movie_rating.c.review_text.is_not(None),
                                                catalogue.rating_shown(now), visible(now)))).scalar()
            if author is None:
                raise ApiError(404, "NOT_FOUND", NO_REVIEW)
            if author == me:
                raise ApiError(403, "FORBIDDEN", OWN_REVIEW)
            await conn.execute(pg_insert(review_vote).values(rating_id=review_id, user_id=me, created_at=now)
                               .on_conflict_do_nothing(index_elements=["rating_id", "user_id"]))
            helpful = (await conn.execute(select(func.count()).select_from(review_vote)
                                          .where(review_vote.c.rating_id == review_id, review_vote.c.created_at <= now))).scalar()
        return {"review_id": review_id, "helpful": helpful, "voted": True}

    return await _guard(write())


# ---- T7: notifications --------------------------------------------------------------------------------------------


class MarkRead(BaseModel):
    """Exactly one of the two: the ids to mark, or all=true."""

    model_config = ConfigDict(extra="forbid")
    ids: list[StrictInt] | None = Field(None, min_length=1, max_length=100)
    all: StrictBool | None = None


@router.get("/notifications")
async def my_notifications(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    return await _guard(rewards.inbox(conn, request.state.caller.id))


@router.post("/notifications/read")
async def read_notifications(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    body = await _json(request, MarkRead)
    if (body.ids is None) == (body.all is not True):
        raise _bad()
    unread = await _guard(rewards.mark_read(conn, request.state.caller.id, body.ids, request.app.state.clock.now()))
    return {"unread": unread}


# ---- T6: profile & settings ---------------------------------------------------------------------------------------

PROFILE_FIELDS = ("display_name", "phone", "preferred_language_id", "preferred_format_id")


class Profile(BaseModel):
    """Every field, every time (a PUT): null clears one. Trimmed here; bounds are checked below so each refusal names
    its own field - the form shows it inline (CR-008 T6). The database CHECKs refuse the same bounds again."""

    model_config = ConfigDict(extra="forbid")
    display_name: StrictStr | None
    phone: StrictStr | None
    preferred_language_id: StrictInt | None
    preferred_format_id: StrictInt | None


PROFILE_ERRORS = {
    "display_name": "Enter a name of 1 to 60 characters, or leave it empty.",
    "phone": "Enter 7 to 15 digits, optionally starting with +.",
    "preferred_language_id": "Choose a language from the list.",
    "preferred_format_id": "Choose a format from the list.",
}


async def _profile(conn: AsyncConnection, user_id: int) -> dict:
    row = (await conn.execute(select(users.c.email, *(users.c[f] for f in PROFILE_FIELDS)).where(users.c.id == user_id))).one()
    return {"email": row.email, **{f: row._mapping[f] for f in PROFILE_FIELDS}}


@router.get("/profile")
async def my_profile(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    async def read():
        out = await _profile(conn, request.state.caller.id)
        await conn.rollback()
        return out

    return await _guard(read())


@router.put("/profile")
async def put_profile(request: Request, conn: AsyncConnection = Depends(db)) -> dict:
    body = await _json(request, Profile)
    values = body.model_dump()
    name = values["display_name"].strip() if values["display_name"] is not None else None
    phone = "".join(values["phone"].split()).replace("-", "") if values["phone"] is not None else None
    values["display_name"], values["phone"] = name or None, phone or None
    errors = {}
    if values["display_name"] is not None and len(values["display_name"]) > 60:
        errors["display_name"] = PROFILE_ERRORS["display_name"]
    if values["phone"] is not None and not re.fullmatch(r"\+?[0-9]{7,15}", values["phone"]):  # ck_users__phone's pattern
        errors["phone"] = PROFILE_ERRORS["phone"]

    async def write():
        async with conn.begin():
            # A preference must name an ACTIVE entry of its lookup, the same list the listing filters offer.
            for field, table in (("preferred_language_id", language), ("preferred_format_id", format_t)):
                if values[field] is not None and (await conn.execute(
                        select(table.c.id).where(table.c.id == values[field], table.c.is_active))).first() is None:
                    errors[field] = PROFILE_ERRORS[field]
            if errors:
                raise ApiError(422, "VALIDATION_FAILED", next(iter(errors.values())), {"fields": errors})
            await conn.execute(update(users).where(users.c.id == request.state.caller.id).values(**values))
            return await _profile(conn, request.state.caller.id)

    return await _guard(write())

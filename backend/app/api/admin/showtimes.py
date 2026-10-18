"""EP-ADM-09..11: one hall's day, create, edit. Nothing else in the system creates a showtime, and there
is no withdraw or cancel route of any kind (P-ADM-21)."""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, current_user, db, get_clock
from app.domain.admin import showtimes
from app.domain.admin.common import BIGINT_MAX, AdminBody, submitted

router = APIRouter()


class ShowtimeCreate(AdminBody):
    movie_id: Any = None
    screen_id: Any = None
    starts_at: Any = None
    ends_at: Any = None
    base_price_paise: Any = None
    format_id: Any = None


class ShowtimePatch(AdminBody):
    version: Any = None
    movie_id: Any = None
    screen_id: Any = None  # accepted only to refuse a different value with its own sentence (P-ADM-09 exc 3)
    starts_at: Any = None
    ends_at: Any = None
    base_price_paise: Any = None
    format_id: Any = None


@router.get("/showtimes")
async def list_day(screen_id: str | None = Query(None), date: str | None = Query(None),
                   include_past: str | None = Query(None), conn=Depends(db), clock=Depends(get_clock)):
    return await showtimes.list_day(conn, screen_id, date, include_past, clock.now())


@router.post("/showtimes", status_code=201)
async def create_showtime(body: ShowtimeCreate, conn=Depends(db), user: CurrentUser = Depends(current_user),
                          clock=Depends(get_clock)):
    return await showtimes.create_showtime(conn, user, submitted(body), clock.now())


@router.patch("/showtimes/{showtime_id}")
async def edit_showtime(body: ShowtimePatch, showtime_id: int = Path(gt=0, le=BIGINT_MAX), conn=Depends(db),
                        user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await showtimes.edit_showtime(conn, user, showtime_id, submitted(body), clock.now())

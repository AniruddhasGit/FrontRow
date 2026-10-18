"""EP-ADM-15..19: halls and adding seats. No DELETE on a hall is mounted (P-ADM-20)."""

from typing import Any

from fastapi import APIRouter, Depends, Path

from app.api.deps import CurrentUser, current_user, db, get_clock
from app.domain.admin import halls
from app.domain.admin.common import AdminBody, submitted

router = APIRouter()


class ScreenCreate(AdminBody):
    cinema_id: Any = None
    name: Any = None


class ScreenPatch(AdminBody):
    version: Any = None
    name: Any = None
    is_active: Any = None


class SeatBatch(AdminBody):
    seats: Any = None


@router.get("/screens")
async def list_screens(conn=Depends(db)):
    return await halls.list_screens(conn)


@router.post("/screens", status_code=201)
async def create_screen(body: ScreenCreate, conn=Depends(db), user: CurrentUser = Depends(current_user),
                        clock=Depends(get_clock)):
    return await halls.create_screen(conn, user, submitted(body), clock.now())


@router.patch("/screens/{screen_id}")
async def edit_screen(body: ScreenPatch, screen_id: int = Path(gt=0), conn=Depends(db),
                      user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await halls.edit_screen(conn, user, screen_id, submitted(body), clock.now())


@router.get("/screens/{screen_id}/seats")
async def list_seats(screen_id: int = Path(gt=0), conn=Depends(db)):
    return await halls.list_seats(conn, screen_id)


@router.post("/screens/{screen_id}/seats", status_code=201)
async def add_seats(body: SeatBatch, screen_id: int = Path(gt=0), conn=Depends(db),
                    user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await halls.add_seats(conn, user, screen_id, submitted(body), clock.now())

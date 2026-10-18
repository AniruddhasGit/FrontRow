"""EP-ADM-28/29: the venue. No POST and no DELETE is mounted; both answer 405 from the global handler."""

from typing import Any

from fastapi import APIRouter, Depends, Path

from app.api.deps import CurrentUser, current_user, db, get_clock
from app.domain.admin import cinemas
from app.domain.admin.common import AdminBody, submitted

router = APIRouter()


class CinemaPatch(AdminBody):
    version: Any = None
    name: Any = None
    timezone: Any = None


@router.get("/cinemas")
async def list_cinemas(conn=Depends(db)):
    return await cinemas.list_cinemas(conn)


@router.patch("/cinemas/{cinema_id}")
async def edit_cinema(body: CinemaPatch, cinema_id: int = Path(gt=0), conn=Depends(db),
                      user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await cinemas.edit_cinema(conn, user, cinema_id, submitted(body), clock.now())

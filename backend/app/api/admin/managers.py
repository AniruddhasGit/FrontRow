"""EP-ADM-22..24: manager accounts and their halls. This creates manager accounts and nothing else."""

from typing import Any

from fastapi import APIRouter, Depends, Path

from app.api.deps import CurrentUser, current_user, db, get_clock, get_settings
from app.domain.admin import managers
from app.domain.admin.common import BIGINT_MAX, AdminBody, submitted

router = APIRouter()


class ManagerCreate(AdminBody):
    email: Any = None
    screen_ids: Any = None


class ManagerScreens(AdminBody):
    screen_ids: Any = None


@router.get("/managers")
async def list_managers(conn=Depends(db)):
    return await managers.list_managers(conn)


@router.post("/managers", status_code=201)
async def create_manager(body: ManagerCreate, conn=Depends(db), user: CurrentUser = Depends(current_user),
                         clock=Depends(get_clock), settings=Depends(get_settings)):
    return await managers.create_manager(conn, user, submitted(body), clock.now(), settings.BCRYPT_COST)


@router.put("/managers/{user_id}/screens")
async def replace_screens(body: ManagerScreens, user_id: int = Path(gt=0, le=BIGINT_MAX), conn=Depends(db),
                          user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await managers.replace_screens(conn, user, user_id, submitted(body), clock.now())

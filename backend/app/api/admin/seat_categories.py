"""EP-ADM-12..14: seat categories and their uplift. No DELETE is mounted (P-ADM-11)."""

from typing import Any

from fastapi import APIRouter, Depends, Path

from app.api.deps import CurrentUser, current_user, db, get_clock, get_settings
from app.domain.admin import seat_categories
from app.domain.admin.common import AdminBody, submitted

router = APIRouter()


class CategoryCreate(AdminBody):
    name: Any = None
    uplift_basis_points: Any = None


class CategoryPatch(AdminBody):
    version: Any = None
    name: Any = None
    uplift_basis_points: Any = None


@router.get("/seat-categories")
async def list_categories(conn=Depends(db), clock=Depends(get_clock), settings=Depends(get_settings)):
    return await seat_categories.list_categories(conn, clock.now(), settings.SALES_CUTOFF_MINUTES)


@router.post("/seat-categories", status_code=201)
async def create_category(body: CategoryCreate, conn=Depends(db), user: CurrentUser = Depends(current_user),
                          clock=Depends(get_clock)):
    return await seat_categories.create_category(conn, user, submitted(body), clock.now())


@router.patch("/seat-categories/{seat_category_id}")
async def edit_category(body: CategoryPatch, seat_category_id: int = Path(gt=0), conn=Depends(db),
                        user: CurrentUser = Depends(current_user), clock=Depends(get_clock),
                        settings=Depends(get_settings)):
    return await seat_categories.edit_category(conn, user, seat_category_id, submitted(body), clock.now(),
                                               settings.SALES_CUTOFF_MINUTES)

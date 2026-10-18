"""EP-ADM-20/21: edit one seat, remove one seat. The freeze is decided in app/domain/admin/halls.py."""

from typing import Any

from fastapi import APIRouter, Depends, Path, Response

from app.api.deps import CurrentUser, current_user, db, get_clock
from app.domain.admin import halls
from app.domain.admin.common import BIGINT_MAX, AdminBody, submitted

router = APIRouter()


class SeatPatch(AdminBody):
    # No version: a seat is not a versioned entity (P-ADM-12, S-ADM-14).
    row_label: Any = None
    seat_number: Any = None
    seat_category_id: Any = None
    grid_row: Any = None
    grid_col: Any = None
    is_active: Any = None


@router.patch("/seats/{seat_id}")
async def edit_seat(body: SeatPatch, seat_id: int = Path(gt=0, le=BIGINT_MAX), conn=Depends(db),
                    user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await halls.edit_seat(conn, user, seat_id, submitted(body), clock.now())


@router.delete("/seats/{seat_id}", status_code=204)
async def delete_seat(seat_id: int = Path(gt=0, le=BIGINT_MAX), conn=Depends(db), user: CurrentUser = Depends(current_user),
                      clock=Depends(get_clock)):
    await halls.delete_seat(conn, user, seat_id, clock.now())
    return Response(status_code=204)

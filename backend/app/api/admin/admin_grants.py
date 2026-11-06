"""EP-ADM-30..32: the emails granted admin access (SRC-008 ROLE-1, S-ADM-30). Authorisation is the router's."""

from typing import Any

from fastapi import APIRouter, Depends, Path, Response

from app.api.deps import CurrentUser, current_user, db, get_clock
from app.domain.admin import admin_grants
from app.domain.admin.common import BIGINT_MAX, AdminBody, submitted

router = APIRouter()


class GrantCreate(AdminBody):
    email: Any = None


@router.get("/admin-grants")
async def list_grants(conn=Depends(db)):
    return await admin_grants.list_grants(conn)


@router.post("/admin-grants", status_code=201)
async def grant(body: GrantCreate, conn=Depends(db), user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    return await admin_grants.grant(conn, user, submitted(body), clock.now())


@router.delete("/admin-grants/{grant_id}", status_code=204)
async def revoke(grant_id: int = Path(gt=0, le=BIGINT_MAX), conn=Depends(db), user: CurrentUser = Depends(current_user),
                 clock=Depends(get_clock)):
    await admin_grants.revoke(conn, user, grant_id, clock.now())
    return Response(status_code=204)

"""EP-ADM-25..27: the four lookup vocabularies. No PUT and no DELETE is mounted: a DELETE here answers 405 from the
global handler, and a rename is refused, never offered (P-ADM-23, P-ADM-24)."""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, current_user, db, get_clock
from app.domain.admin import lookups
from app.domain.admin.common import BIGINT_MAX, AdminBody, invalid, submitted

router = APIRouter()


class LookupCreate(AdminBody):
    name: Any = None


class LookupPatch(AdminBody):
    is_active: Any = None


@router.get("/lookups/{kind}")
async def list_entries(kind: str, include_withdrawn: str | None = Query(None), conn=Depends(db)):
    lookups.table(kind)  # the address first: a fifth vocabulary is a page that does not exist (404), never a 422
    flags = {None: False, "false": False, "true": True}
    if include_withdrawn not in flags:
        raise invalid("include_withdrawn")
    return await lookups.list_entries(conn, kind, flags[include_withdrawn])


@router.post("/lookups/{kind}", status_code=201)
async def create_entry(body: LookupCreate, kind: str, conn=Depends(db), user: CurrentUser = Depends(current_user),
                       clock=Depends(get_clock)):
    lookups.table(kind)
    return await lookups.create_entry(conn, user, kind, submitted(body), clock.now())


@router.patch("/lookups/{kind}/{id}")
async def set_active(body: LookupPatch, kind: str, id: int = Path(gt=0, le=BIGINT_MAX), conn=Depends(db),  # noqa: A002
                     user: CurrentUser = Depends(current_user), clock=Depends(get_clock)):
    lookups.table(kind)
    # Not submitted(): this address refuses an unknown property with its own sentence (P-ADM-24 exception 5).
    fields = {**(body.model_extra or {}), **{n: getattr(body, n) for n in body.model_fields_set}}
    return await lookups.set_active(conn, user, kind, id, fields, clock.now())

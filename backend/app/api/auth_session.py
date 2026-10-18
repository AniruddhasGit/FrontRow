"""SESSION router at /api/auth: the signed-in caller's identity (EP-ACC-04). Every route here gets
current_user from the router; a handler reads the user with `Depends(current_user)`, which FastAPI
resolves once per request."""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, current_user
from app.domain import accounts

router = APIRouter(prefix="/api/auth", dependencies=[Depends(current_user)])


@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)) -> dict:
    # Read from the users row on this request (deps.current_user), never from the token's claims, so a
    # role changed in the database shows here on the very next call.
    return accounts.identity_of(user)

"""Admin access by email (SRC-008 ROLE-1 and its ADDENDUM, S-ADM-30; EP-ADM-30..32).

An admin types an address; when someone registers or signs in with it (trimmed, case-insensitive) their account
becomes admin - app/domain/accounts does that, reading this table. Removing the address makes an admin account
with it a customer AT ONCE, in the same transaction as the delete and its audit row. The seeded admin is never on
the list: an address that already belongs to an admin is refused, so the system cannot be left with no admin through
this list, and an admin cannot remove their own address. The refusal sentences are [JUDGMENT CALL] wording: no P-row
publishes any (S-ADM-30).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.accounts import Role, checked_email
from app.domain.admin.common import audit, constraint_name, invalid, not_found, transaction, utc_text
from app.models import admin_grant, users

ALREADY_GRANTED = "That email address already has admin access."
ALREADY_ADMIN = "That account is already an admin. Only addresses that are not admins yet can be added."
OWN_EMAIL = "You cannot remove your own email address. Ask another admin to remove it."
GRANT_GONE = "That email address is no longer on the list. Reload the page."
_COLS = (admin_grant.c.id, admin_grant.c.email, admin_grant.c.granted_by, admin_grant.c.created_at)


def _out(row: Any) -> dict:
    return {"id": row.id, "email": row.email, "granted_by": row.granted_by, "created_at": utc_text(row.created_at)}


async def list_grants(conn: AsyncConnection) -> dict:
    rows = (await conn.execute(select(*_COLS).order_by(admin_grant.c.email, admin_grant.c.id))).all()
    return {"items": [_out(r) for r in rows]}


async def grant(conn: AsyncConnection, actor: Any, fields: dict, now: datetime) -> dict:
    email = checked_email(fields.get("email")).lower()  # register's own rules; stored lower-case
    try:
        async with transaction(conn, ("admin_grant.created",)):
            if await conn.scalar(select(func.count()).select_from(admin_grant).where(admin_grant.c.email == email)):
                raise invalid("email", ALREADY_GRANTED)
            if await conn.scalar(select(func.count()).select_from(users).where(
                    func.lower(users.c.email) == email, users.c.role == Role.ADMIN.value)):
                raise invalid("email", ALREADY_ADMIN)
            row = (await conn.execute(insert(admin_grant).values(email=email, granted_by=actor.id).returning(*_COLS))).one()
            await audit(conn, actor, "admin_grant.created", "admin_grant", row.id, None, {"email": email}, now)
            return _out(row)
    except IntegrityError as exc:
        if constraint_name(exc) == "uq_admin_grant__email_ci":
            raise invalid("email", ALREADY_GRANTED) from None  # a simultaneous twin won
        raise


async def revoke(conn: AsyncConnection, actor: Any, grant_id: int, now: datetime) -> None:
    async with transaction(conn, ("admin_grant.deleted",)):
        # The delete is the read: a twin removal finds nothing (404). Refusing one's own address raises inside the
        # block, so the delete rolls back with it.
        email = await conn.scalar(delete(admin_grant).where(admin_grant.c.id == grant_id).returning(admin_grant.c.email))
        if email is None:
            raise not_found(GRANT_GONE)
        if email == actor.email.lower():
            raise invalid("grant_id", OWN_EMAIL)
        demoted = await conn.scalar(update(users).where(func.lower(users.c.email) == email, users.c.role == Role.ADMIN.value)
                                    .values(role=Role.CUSTOMER.value).returning(users.c.id))
        # entity_id is the key the removed row HELD (as manager.screen_unassigned); after names the demoted account.
        await audit(conn, actor, "admin_grant.deleted", "admin_grant", grant_id, {"email": email},
                    {"demoted_user_id": demoted} if demoted else None, now)

"""Manager accounts and the halls each may read (P-ADM-17). PROVISIONAL role set (SRC-003 C-1).

The admin creates role manager and nothing else; no endpoint creates an admin. The account gets NO
USABLE PASSWORD: password_hash is a real bcrypt digest of a random secret that is never stored or
shown, so no two accounts share a value and no password signs in. The manager sets one through password
reset (Phase 5, SRC-004 JC-R6-02). The product sends nothing: no outbox row, no SES message.
Nothing enforces "two managers per hall" - zero, one or three are all valid (FR-ADR-011).
No credential field ever enters an audit row.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from typing import Any

import anyio
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.security import hash_password
from app.domain.admin.common import audit, constraint_name, invalid, is_int, not_found, transaction, utc_text
from app.models import manager_screen_assignment as msa
from app.models import screen, users

MANAGER = "manager"
EMAIL_TAKEN = ("An account already exists with that email address. Accounts are never removed, so an address stays "
               "in use once it has been registered.")
EMAIL_BAD = "Enter a valid email address."
HALL_GONE = "One of those halls no longer exists. Reload the page and choose again."
HALL_TWICE = "That hall is listed twice. Choose each hall once."
NOT_A_MANAGER = "That account is not a manager account. Screens can only be assigned to managers."
ACCOUNT_GONE = "That account no longer exists at this address."
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _email(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 254 or not _EMAIL.fullmatch(value.strip()):
        raise invalid("email", EMAIL_BAD)
    return value.strip()


def _screen_ids(value: Any) -> list[int]:
    if not isinstance(value, list) or not all(is_int(v) for v in value):
        raise invalid("screen_ids")
    if len(set(value)) != len(value):
        raise invalid("screen_ids", HALL_TWICE)
    return value


async def _check_screens(conn: AsyncConnection, ids: list[int]) -> None:
    if ids and await conn.scalar(select(func.count()).select_from(screen).where(screen.c.id.in_(ids))) != len(ids):
        raise invalid("screen_ids", HALL_GONE)


async def _assigned(conn: AsyncConnection, user_id: int) -> list[dict]:
    return [dict(r) for r in (await conn.execute(select(msa.c.id, msa.c.screen_id).where(msa.c.user_id == user_id)
                                                 .order_by(msa.c.screen_id))).mappings()]


async def _assign(conn: AsyncConnection, actor: Any, user_id: int, screen_ids: list[int], now: datetime) -> None:
    for sid in screen_ids:
        new_id = await conn.scalar(insert(msa).values(user_id=user_id, screen_id=sid).returning(msa.c.id))
        await audit(conn, actor, "manager.screen_assigned", "manager_screen_assignment", new_id, None,
                    {"user_id": user_id, "screen_id": sid}, now)


async def list_managers(conn: AsyncConnection) -> dict:
    rows = (await conn.execute(select(users.c.id, users.c.email, users.c.last_signed_in_at, users.c.created_at)
                               .where(users.c.role == MANAGER).order_by(users.c.email, users.c.id))).all()
    pairs = (await conn.execute(select(msa.c.user_id, msa.c.screen_id).order_by(msa.c.screen_id))).all()
    return {"items": [{"user_id": r.id, "email": r.email,
                       "assigned_screen_ids": [p.screen_id for p in pairs if p.user_id == r.id],
                       "has_signed_in": r.last_signed_in_at is not None, "created_at": utc_text(r.created_at)}
                      for r in rows]}


async def create_manager(conn: AsyncConnection, actor: Any, fields: dict, now: datetime, bcrypt_cost: int) -> dict:
    email = _email(fields.get("email"))
    screen_ids = _screen_ids(fields.get("screen_ids"))
    # bcrypt is ~300 ms of CPU: off the event loop (app/core/security.py).
    unusable = await anyio.to_thread.run_sync(hash_password, secrets.token_urlsafe(32), bcrypt_cost)
    try:
        async with transaction(conn, ("manager.created", "manager.screen_assigned")):
            if await conn.scalar(select(func.count()).select_from(users).where(func.lower(users.c.email) == email.lower())):
                raise invalid("email", EMAIL_TAKEN)
            await _check_screens(conn, screen_ids)
            user_id = await conn.scalar(insert(users).values(email=email, password_hash=unusable, role=MANAGER,
                                                             password_version=1).returning(users.c.id))
            await audit(conn, actor, "manager.created", "user", user_id, None, {"email": email, "role": MANAGER}, now)
            await _assign(conn, actor, user_id, screen_ids, now)
            return {"user_id": user_id, "email": email, "assigned_screen_ids": sorted(screen_ids)}
    except IntegrityError as exc:
        if constraint_name(exc) == "uq_users__email_ci":
            raise invalid("email", EMAIL_TAKEN) from None
        raise


async def replace_screens(conn: AsyncConnection, actor: Any, user_id: int, fields: dict, now: datetime) -> dict:
    """EP-ADM-24: the complete set is sent; the server writes the difference, so a repeat writes nothing."""
    screen_ids = _screen_ids(fields.get("screen_ids"))
    async with transaction(conn, ("manager.screen_assigned", "manager.screen_unassigned")):
        role = await conn.scalar(select(users.c.role).where(users.c.id == user_id).with_for_update())
        if role is None:
            raise not_found(ACCOUNT_GONE)
        if role != MANAGER:
            raise invalid("user_id", NOT_A_MANAGER)
        await _check_screens(conn, screen_ids)
        current = await _assigned(conn, user_id)
        for row in current:
            if row["screen_id"] not in screen_ids:
                await conn.execute(delete(msa).where(msa.c.id == row["id"]))
                # entity_id is the key the removed row HELD; it deliberately resolves to nothing (P-ADM-19).
                await audit(conn, actor, "manager.screen_unassigned", "manager_screen_assignment", row["id"],
                            {"user_id": user_id, "screen_id": row["screen_id"]}, None, now)
        held = {r["screen_id"] for r in current}
        await _assign(conn, actor, user_id, [s for s in screen_ids if s not in held], now)
        return {"user_id": user_id, "assigned_screen_ids": sorted(screen_ids)}

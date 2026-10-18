"""Write the audit row in the CALLER's transaction (P-XCT-03, FR-ADR-019, P-ADM-19).

Usage, in an admin handler - the change and its audit row commit together or not at all:

    check_action("showtime.base_price_changed")          # BEFORE the transaction opens
    async with conn.begin():
        await conn.execute(update(showtime)...)
        await write_audit(conn, actor=user, action="showtime.base_price_changed",
                          entity_type="showtime", entity_id=41,
                          before={"base_price_paise": 25000}, after={"base_price_paise": 28000},
                          occurred_at=clock.now())

write_audit never opens, commits or rolls back anything: if it raises, the caller's `begin()` block
rolls the change back with it. The application role can INSERT and SELECT audit_log and nothing else,
so an UPDATE or DELETE here would be refused by the database (S-XCT-07) - there is none.

`before` / `after` carry ONLY the changed fields (never a whole row, never a credential); `before` is
None for a creation. `actor_role` is COPIED from the user row loaded for this request, never joined at
read time, because a role can change later.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import insert, null
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.logging import get_request_id
from app.domain.audit import AUDIT_ACTIONS
from app.models import audit_log


class Actor(Protocol):
    id: int
    role: str


class UnknownAuditAction(Exception):
    """An action outside the closed vocabulary. Unhandled on purpose: it renders as 500 INTERNAL_ERROR."""


def check_action(action: str) -> None:
    """The boundary check. Call it before opening the transaction (P-XCT-03 exception 4)."""
    if action not in AUDIT_ACTIONS:
        raise UnknownAuditAction(action)


async def write_audit(
    conn: AsyncConnection,
    *,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: int,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    occurred_at: datetime,
) -> None:
    check_action(action)  # again, so a caller that forgot the early check still cannot write a non-member
    if occurred_at.tzinfo is None or occurred_at.utcoffset() != timedelta(0):
        # The column is timestamptz in UTC. A naive or non-UTC instant is a caller bug, not data.
        raise ValueError("occurred_at must be an aware UTC datetime (inject Clock.now())")
    await conn.execute(
        insert(audit_log).values(
            occurred_at=occurred_at,
            actor_user_id=actor.id,
            actor_role=actor.role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            # null(), not None: SQLAlchemy writes a Python None into JSONB as the JSON value `null`, and
            # `before IS NULL` (a creation) would then be false.
            before=before if before is not None else null(),
            after=after if after is not None else null(),
            # The request id from the log context, so the audit row joins to the log lines (FR-ADR-056).
            request_id=get_request_id(),
        )
    )

"""Shared admin rules: field validation with the PRD's own sentences, naive-local time, versions, locks.

Validation order on every versioned PATCH is P-ADM-12's: version -> field validation -> no-op -> write.
Unknown body properties are 400 REQUEST_INVALID, never dropped (E6 S4 "Unknown properties are rejected").
"""

from __future__ import annotations

import enum
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.errors import ApiError
from app.core.audit import check_action, write_audit
from app.domain.audit import AUDIT_ACTIONS
from app.domain.money import BIGINT_MAX
from app.domain.pricing import seat_price_paise

# The closed action vocabulary as an enum (S-ADM-02). Built from the one tuple, so there is no second list:
# AuditAction("screen.exploded") raises ValueError.
AuditAction = enum.StrEnum("AuditAction", {a.replace(".", "__").upper(): a for a in AUDIT_ACTIONS})

DB_DOWN = "The system cannot reach its database right now. Nothing was saved. Try again in a moment."
STALE_FORM = "This form is out of date. Reload the page and make the change again."


class AdminBody(BaseModel):
    """Every admin request body. Fields are declared (so the route's schema names them) but typed Any:
    the sentences a failing field answers with are the PRD's, so the domain validates, not pydantic.
    extra="allow" only so the domain can SEE an unknown property and refuse it with 400."""

    model_config = ConfigDict(extra="allow")


def submitted(body: AdminBody) -> dict[str, Any]:
    """The fields the request actually carried. An unknown one is 400 REQUEST_INVALID (E6 S4)."""
    if body.model_extra:
        # details.field names the property (E8 SCR-XCT-01 details table: `field` where one can be named); with
        # several, the first in sorted order, so the same body always names the same one.
        raise ApiError(400, "REQUEST_INVALID", details={"field": sorted(body.model_extra)[0]})
    return {name: getattr(body, name) for name in body.model_fields_set}


def invalid(field: str, message: str | None = None, **details: Any) -> ApiError:
    return ApiError(422, "VALIDATION_FAILED", message, {"field": field, **details})


def not_found(message: str) -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


# PostgreSQL's integer widths. A value past the column's width is a validation failure (422), never a
# DataError from the driver (500): every id here is bigint, and seat_number / grid_row / grid_col are integer.
INT4_MAX = 2**31 - 1


def is_int(value: Any) -> bool:
    # bool is an int subclass; 25000.0 is a float. Neither is a whole number of anything here. A whole number
    # outside bigint cannot be stored or even compared by the database, so it is not one here either.
    return type(value) is int and -BIGINT_MAX - 1 <= value <= BIGINT_MAX


def need_int(value: Any, field: str, *, minimum: int = 1, maximum: int = BIGINT_MAX, wrong: str | None = None,
             low: str | None = None) -> int:
    if not is_int(value) or value > maximum:
        raise invalid(field, wrong)
    if value < minimum:
        raise invalid(field, low or wrong)
    return value


def need_bool(value: Any, field: str, message: str | None = None) -> bool:
    if type(value) is not bool:
        raise invalid(field, message)
    return value


def need_name(value: Any, field: str, maximum: int, message: str) -> str:
    """Trimmed, 1..maximum characters after trimming. Stored trimmed."""
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise invalid(field, message)
    return value.strip()


def need_version(fields: dict[str, Any]) -> int:
    """A write with no version is 422, never last-write-wins (P-ADM-12 exception 5)."""
    if not is_int(fields.get("version")):
        raise invalid("version", STALE_FORM)
    return fields.pop("version")


def check_version(stored: int, sent: int, message: str) -> None:
    if stored != sent:
        raise ApiError(409, "VERSION_CONFLICT", message)


def check_ceiling(base: int, uplift: int) -> bool:
    """FR-ADR-038's numerator must fit PostgreSQL bigint (P-ADM-10, P-ADM-11). Arithmetic, not business.
    Asked of the one formula itself (app/domain/pricing.py refuses a numerator past bigint), so the ceiling
    and the price can never disagree about where the edge is."""
    try:
        seat_price_paise(base, uplift)
    except OverflowError:
        return False
    return True


# Any fixed bigint; it names the one pairwise ceiling below and nothing else takes it.
_PRICE_CEILING_LOCK = 0x46525052494345  # "FRPRICE"


async def lock_price_ceiling(conn: AsyncConnection) -> None:
    """Serialise the two mirror ceilings (P-ADM-10 against the highest uplift, P-ADM-11 against the highest base
    price). Each reads the OTHER table's maximum; without a shared lock a showtime create and an uplift raise
    can each pass against the other's old value and together store a pair whose price overflows bigint
    (write skew). Transaction-scoped: released at COMMIT or ROLLBACK, so it needs no cleanup."""
    await conn.execute(select(func.pg_advisory_xact_lock(_PRICE_CEILING_LOCK)))


# ---- admin datetimes are naive local in both directions (E6 S4) ------------------------------------------

_NAIVE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")


def parse_local(value: Any, field: str, message: str) -> datetime:
    """A naive local date and time. A Z, an offset or a zone name is 422 and is never coerced (P-ADM-04)."""
    if not isinstance(value, str) or not _NAIVE.fullmatch(value):
        raise invalid(field, message)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise invalid(field, message) from None


def to_utc(local: datetime, zone: str) -> datetime:
    return local.replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)


def to_local(instant: datetime, zone: str) -> str:
    return instant.astimezone(ZoneInfo(zone)).replace(tzinfo=None).isoformat(timespec="seconds")


def utc_text(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def join_labels(labels: list[str]) -> str:
    """'A', 'A and B', 'A, B and C' (P-ADM-13)."""
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


# ---- the one transaction --------------------------------------------------------------------------------


@asynccontextmanager
async def transaction(conn: AsyncConnection, actions: Iterable[str]) -> AsyncIterator[None]:
    """Check every action this write may audit BEFORE BEGIN (P-XCT-03 exception 4), then open the one
    transaction the change and its audit rows share. A lost connection is 503, nothing written."""
    for action in actions:
        check_action(action)
    try:
        async with conn.begin():
            yield
    except (OperationalError, InterfaceError) as exc:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", DB_DOWN) from exc


async def audit(conn: AsyncConnection, actor: Any, action: str, entity_type: str, entity_id: int,
                before: dict | None, after: dict | None, now: datetime) -> None:
    await write_audit(conn, actor=actor, action=action, entity_type=entity_type, entity_id=entity_id,
                      before=before, after=after, occurred_at=now)


def constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None) or ""

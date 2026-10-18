"""S-SCP-11 (P-SCP-05, SRC-001 §6.5): no point-of-sale integration.

The confirmation half of the listener is below, at the Core level. Still Blocked: the criterion names a mapper-level
before_insert listener (no ORM mapper exists) and scripts/seed.py writes booking_seat with psycopg COPY.
"""

from __future__ import annotations

import pytest

from tests.xct._support import rg


def test_no_point_of_sale_vocabulary_in_the_application():
    assert rg(r"\bpos\b|\btill\b|counter_?sale|terminal_?sale", "backend/app", "frontend/src", ignore_case=True) == []


@pytest.mark.anyio
async def test_every_booking_seat_insert_on_the_confirm_path_originates_in_app_domain(migrated_db, monkeypatch):
    """The confirmation half of the criterion's listener, at the Core level (no ORM mapper exists in this codebase):
    every INSERT INTO booking_seat the application sends is traced to the modules on its call stack, and the only
    application module originating one is app.domain.booking. scripts/seed.py writes with psycopg COPY, which no
    SQLAlchemy listener can see - that half is the doc defect reported with this row."""
    import inspect

    from sqlalchemy.ext.asyncio import AsyncConnection

    from tests.pay.kit import C1, api, clock_at, confirm, hold, user, world7

    db = world7(migrated_db)["db"]
    u = user(db)
    origins: set[str] = set()

    real = AsyncConnection.execute

    # At the async boundary, where the awaiting coroutines' frames are still on the stack (the driver's own
    # cursor event runs in a greenlet that has lost them).
    async def trace(self, statement, *args, **kwargs):
        if str(statement).lstrip().upper().startswith("INSERT INTO BOOKING_SEAT"):
            names = {getattr(inspect.getmodule(f.frame), "__name__", "") for f in inspect.stack()}
            origins.update(n for n in names if n.startswith("app."))
        return await real(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncConnection, "execute", trace)

    async with api(db, clock_at()) as c:
        h = await hold(c, u, [C1])
        assert (await confirm(c, u, h["hold_token"])).status_code == 201
    domain = {n for n in origins if n.startswith("app.domain")}
    assert domain == {"app.domain.booking"}, origins

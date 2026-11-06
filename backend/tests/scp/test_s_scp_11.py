"""S-SCP-11 (P-SCP-05, SRC-001 §6.5): no point-of-sale integration.

The confirmation half of the listener is below, at the Core level. Still Blocked: the criterion names a mapper-level
before_insert listener (no ORM mapper exists) and scripts/seed.py writes booking_seat with psycopg COPY.
"""

from __future__ import annotations

import pytest

from tests.xct._support import rg


POS = r"point[-_ ]?of[-_ ]?sale|\bpos[-_/]|[-_/]pos\b|\bpos(terminal|sale|_?id)\b|\btill\b|counter_?sale|terminal_?sale"


def test_no_point_of_sale_vocabulary_in_the_application():
    """CR-002 A-7: a bare `pos` (a byte offset in domain/posters.py) no longer counts; every POS shape still does."""
    import re

    from tests.scp.test_s_scp_01 import EXCLUDED

    assert rg(POS, "backend/app", "frontend/src", ignore_case=True) == []
    rx = re.compile(POS, re.IGNORECASE)
    assert all(rx.search(s) for s in ("Point of Sale", "pos_id", "/pos", "pos-sale", "possale", "posTerminal", "till"))
    assert EXCLUDED.search("/api/pos/sales")  # S-SCP-01's mounted-path regex still refuses pos/


def test_exactly_two_code_sites_write_booking_seat():
    hits = rg(r"insert\(booking_seat\)|INSERT INTO booking_seat|COPY booking_seat", "backend/app", "scripts", ignore_case=True)
    files = {h[0] for h in hits}
    domain = [f for f in files if f.startswith("backend/app/domain/")]
    assert len(domain) == 1 and files == {domain[0], "scripts/seed.py"}, files


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

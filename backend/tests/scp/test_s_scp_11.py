"""S-SCP-11 (P-SCP-05, SRC-001 §6.5): no point-of-sale integration.

The point-of-sale sweep, the two-writer census, and the run-time trace with a Core before_cursor_execute listener on
the engine, as the cell names it. The seed's COPY count is asserted in tests/xct/test_s_xct_45.py.
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
async def test_every_booking_seat_insert_on_the_confirm_path_originates_in_app_domain(migrated_db):
    """A Core before_cursor_execute listener on the app's engine records inspect.getmodule(frame).__name__ for every
    frame at each INSERT INTO booking_seat across a full confirm. SQLAlchemy's async layer runs the cursor call in a
    child greenlet, so the frames are this greenlet's stack PLUS its parent's suspended stack (greenlet.parent.gr_frame
    and its f_back chain), which holds the awaiting coroutines - the application's modules."""
    import inspect

    import greenlet
    from sqlalchemy import event

    from tests.pay.kit import C1, api, clock_at, confirm, hold, user, world7

    db = world7(migrated_db)["db"]
    u = user(db)
    origins: list[set[str]] = []

    def frames():
        f = inspect.currentframe()
        g = greenlet.getcurrent()
        while True:
            while f is not None:
                yield f
                f = f.f_back
            g = g.parent
            if g is None:
                return
            f = g.gr_frame

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO BOOKING_SEAT"):
            origins.append({getattr(inspect.getmodule(f), "__name__", "") for f in frames()})

    async with api(db, clock_at()) as c:
        engine = c.application.state.db_engine.sync_engine
        event.listen(engine, "before_cursor_execute", record)
        try:
            h = await hold(c, u, [C1])
            assert (await confirm(c, u, h["hold_token"])).status_code == 201
        finally:
            event.remove(engine, "before_cursor_execute", record)
    assert origins, "the confirm sent no INSERT INTO booking_seat the listener saw"
    for names in origins:
        assert {n for n in names if n.startswith("app.domain.")} == {"app.domain.booking"}, names

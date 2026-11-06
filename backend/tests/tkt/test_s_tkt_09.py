"""S-TKT-09 (P-TKT-06, SCR-TKT-02): the receipt carries everything needed at a door and nothing else."""

from __future__ import annotations

import pytest

from tests.tkt.kit import Clock, booking, message, owner_sql, set_claim, truncate, worker

pytestmark = pytest.mark.anyio

# SCR-TKT-02's plain-text body, verbatim: 15 lines, LF, five blank lines, every value at column 11.
PLAIN = (
    "Your booking is confirmed.\n"
    "\n"
    "Booking reference: FR-ACDE-FHJD\n"
    "\n"
    "Film      DEMO MOVIE 01\n"
    "Hall      Hall 3\n"
    "Showtime  21 Aug 2026, 7:15 pm (Asia/Kolkata)\n"
    "Seats     F7, F8, F9\n"
    "Paid      $843.72\n"
    "\n"
    "Show this reference at the entrance. A person will check it.\n"
    "\n"
    "You can see this booking again at https://example.invalid/bookings/FR-ACDE-FHJD\n"
    "\n"
    "This booking is final. There is no cancellation and no refund.\n"
)


def test_the_literal_above_is_the_block_published_under_copy_in_e4():
    """The cell compares against the E4 Copy block byte for byte; PLAIN must be that block, not a private copy."""
    from tests.xct._support import REPO

    e4 = (REPO / "docs/03 PRD/sections/E4_receipt_entry.md").read_text(encoding="utf-8")
    after = e4.split("Plain-text body, verbatim, with the bracketed values substituted:\n\n```\n", 1)[1]
    assert after.split("```\n", 1)[0] == PLAIN


@pytest.fixture
def db(migrated_db):
    truncate(migrated_db)
    return migrated_db


async def _send(db, b, seq=1):
    w = worker(db, Clock())
    try:
        assert await w.handle(message(b, dispatch_seq=seq)) is True
    finally:
        await w.engine.dispose()
    (to, msg), = w.transport.calls
    return to, msg


async def test_the_receipt_is_the_published_copy_byte_for_byte(db):
    b = booking(db)
    to, msg = await _send(db, b)
    assert to == "name@example.com"
    plain = msg.get_body(("plain",)).get_content()
    assert plain == PLAIN and len(plain.splitlines()) == 15 and "₹" not in plain
    assert msg["Subject"] == "Your FrontRow booking FR-ACDE-FHJD"
    html = msg.get_body(("html",)).get_content()
    assert "$843.72" in html and "See this booking again" in html
    assert html.count("href=") == 1 and 'href="https://example.invalid/bookings/FR-ACDE-FHJD"' in html
    for banned in ("<img", "<table", "<td"):
        assert banned not in html
    parts = list(msg.walk())
    assert not any(p.get_content_disposition() == "attachment" for p in parts)
    assert not any(p.get_content_type().startswith("image/") for p in parts)


async def test_a_resend_is_byte_identical_and_every_field_is_read_at_send_time(db):
    b = booking(db)
    _, first = await _send(db, b)
    # The resend raises dispatch_seq and returns the row to pending (P-TKT-07); the body must not change.
    owner_sql(db, "UPDATE receipt_dispatch SET status = 'pending', dispatch_seq = 2 WHERE booking_id = %s", (b,))
    _, second = await _send(db, b, seq=2)
    assert second.get_body(("plain",)).get_content() == first.get_body(("plain",)).get_content()
    assert second.get_body(("html",)).get_content() == first.get_body(("html",)).get_content()
    # Between the enqueue and the send the title changes: the sent body carries the new one, from PostgreSQL.
    owner_sql(db, "UPDATE receipt_dispatch SET status = 'pending', dispatch_seq = 3 WHERE booking_id = %s", (b,))
    owner_sql(db, "UPDATE movie SET title = 'DEMO MOVIE 02'")
    _, third = await _send(db, b, seq=3)
    assert "Film      DEMO MOVIE 02\n" in third.get_body(("plain",)).get_content()


async def test_a_suppressed_row_renders_nothing(db):
    b = booking(db)
    set_claim(db, b, "suppressed")
    w = worker(db, Clock())
    try:
        await w.handle(message(b))
    finally:
        await w.engine.dispose()
    assert w.transport.calls == []

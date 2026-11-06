"""S-TKT-12 (P-TKT-08): nothing is built for the door, and that is proved - the backend half.

Presenting a reference twice through GET /api/bookings/by-reference/FR-ACDE-FHJD (EP-TKT-01) writes nothing: every
public table's row count is identical before and after. The SCR-TKT-01 entrance line is asserted in
frontend/src/features/ticket/ticket.test.mjs (ENTRY). `python -m pip freeze` is read as importlib.metadata, the same
dist-info pip freeze reads, because the image's venv is built --without-pip."""

from __future__ import annotations

import importlib.metadata
import json

import pytest

from tests.tkt.kit import Clock, booking, message, truncate, worker
from tests.xct._support import REPO
from tests.dbkit import app_sql, owner_sql
from tests.pay.kit import api, clock_at, cookies, flush

pytestmark = pytest.mark.anyio
CONTRACT = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))


def test_no_door_endpoint_and_exactly_two_owner_only_reference_endpoints():
    paths = [e["path"] for e in CONTRACT["endpoints"]]
    for banned in ("/validate", "/scan", "/checkin", "/check-in", "/door", "/admit", "/tickets"):
        assert not [p for p in paths if banned in p], banned
    ref = [e for e in CONTRACT["endpoints"] if e["path"].startswith("/api/bookings/by-reference/")]
    assert sorted(e["id"] for e in ref) == ["EP-TKT-01", "EP-TKT-02"]
    assert all("user_id equals their own user id" in e["authorisation_rule"] for e in ref)


def test_no_response_declares_an_image_content_type():
    assert "image/" not in json.dumps([e["responses"] for e in CONTRACT["endpoints"]])


def test_the_booking_table_has_no_entry_column(migrated_db):
    assert app_sql(migrated_db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'booking' "
                                "AND column_name IN ('used_at','admitted_at','scanned_at','checked_in_at','entry_at')") == [(0,)]


def test_the_installed_distributions_include_no_code_or_image_library():
    # `python -m pip freeze` in the AC: the image has no pip (the venv is built --without-pip), so the same list is read
    # from the installed distributions' metadata - what pip freeze itself reads.
    installed = {d.metadata["Name"].lower() for d in importlib.metadata.distributions()}
    assert installed & {"qrcode", "segno", "pyqrcode", "python-barcode", "treepoem", "pyzbar", "reportlab"} == set()


async def test_the_sent_receipt_has_no_attachment_and_no_image_part(migrated_db):
    truncate(migrated_db)
    b = booking(migrated_db)
    w = worker(migrated_db, Clock())
    try:
        await w.handle(message(b))
    finally:
        await w.engine.dispose()
    (_, msg), = w.transport.calls
    assert [p for p in msg.walk() if p.get_content_disposition() == "attachment" or p.get_content_type().startswith("image/")] == []
    assert "Show this reference at the entrance. A person will check it.\n" in msg.get_body(("plain",)).get_content()


def _counts(db) -> dict[str, int]:
    tables = [t for (t,) in owner_sql(db, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                                          "AND table_type = 'BASE TABLE' ORDER BY 1")]
    return {t: owner_sql(db, f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}


async def test_presenting_one_reference_twice_writes_nothing(migrated_db):
    truncate(migrated_db)
    flush()
    b = booking(migrated_db)
    owner = owner_sql(migrated_db, "SELECT user_id FROM booking WHERE id = %s", (b,))[0][0]
    before = _counts(migrated_db)
    async with api(migrated_db, clock_at()) as c:
        for _ in range(2):
            r = await c.get("/api/bookings/by-reference/FR-ACDE-FHJD", cookies=cookies(c, owner))
            assert r.status_code == 200, r.text
    after = _counts(migrated_db)
    assert "audit_log" in before and len(before) > 10
    assert after == before

"""S-TKT-12 (P-TKT-08): nothing is built for the door, and that is proved - the backend half.

NOT covered here: presenting a reference twice through GET /api/bookings/by-reference/{r} (EP-TKT-01 is not mounted
yet) and the SCR-TKT-01 render (frontend)."""

from __future__ import annotations

import importlib.metadata
import json

import pytest

from tests.tkt.kit import Clock, booking, message, truncate, worker
from tests.xct._support import REPO
from tests.dbkit import app_sql

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

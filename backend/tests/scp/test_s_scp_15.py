"""S-SCP-15 (P-SCP-09/10, OPEN-TICKET-01): no scannable artefact is generated in the receipt - the backend half.

Covered: the message the worker hands to the stub transport, read back from the transport's stdout with
email.message_from_string; the no-QR-library scan. NOT covered here: the confirmation and booking pages' DOM (frontend,
SCR-TKT-01) and the rendered BOOKING REFERENCE element."""

from __future__ import annotations

import email
import io
import json
import re

import pytest

from app.domain.mail import StubTransport
from tests.tkt.kit import Clock, booking, message, truncate, worker
from tests.xct._support import rg

pytestmark = pytest.mark.anyio


async def test_the_stub_transports_message_has_no_attachment_no_image_and_no_inline_image(migrated_db):
    truncate(migrated_db)
    b = booking(migrated_db)
    out = io.StringIO()
    w = worker(migrated_db, Clock(), mail=StubTransport(out))
    try:
        assert await w.handle(message(b)) is True
    finally:
        await w.engine.dispose()
    (line,) = out.getvalue().splitlines()
    msg = email.message_from_string(json.loads(line)["mime"])
    parts = list(msg.walk())
    assert not any(p.get_content_disposition() == "attachment" for p in parts)
    assert not any(p.get_content_type().startswith("image/") for p in parts)
    html = next(p for p in parts if p.get_content_type() == "text/html").get_payload(decode=True).decode()
    assert not re.search(r"<img\b", html, re.I) and "cid:" not in html and "data:image" not in html
    # The stub's line is a log line: the reference may be in it, the recipient's address may not (FR-ADR-056).
    assert "name@example.com" not in line and msg["To"] == "[REDACTED]"


def test_no_qr_or_barcode_library_is_named_anywhere():
    assert rg(r"qrcode|qr_code|barcode|segno|zxing|pyzbar", "backend/app", "backend/migrations", "frontend/src", ignore_case=True) == []

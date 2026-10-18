"""S-TKT-13 (P-TKT-10/11): the receipt's dispatch state stays off the customer API and a failed send writes no message -
the worker and repository half.

NOT covered here: GET /api/bookings/by-reference/{r} bodies for a `sent` and a `failed` booking (EP-TKT-01 is not
mounted yet) and the SCR-TKT-01 DOM comparison (frontend)."""

from __future__ import annotations

import json

import pytest

from tests.dbkit import app_sql
from tests.tkt.kit import Clock, Mail, booking, message, owner_sql, truncate, worker
from tests.xct._support import REPO, rg

pytestmark = pytest.mark.anyio


async def test_a_failed_send_changes_no_column_of_the_booking(migrated_db):
    truncate(migrated_db)
    b = booking(migrated_db)
    before = owner_sql(migrated_db, "SELECT * FROM booking WHERE id = %s", (b,))
    mail = Mail()
    mail.refuse = True
    w = worker(migrated_db, Clock(), mail=mail)
    try:
        assert await w.handle(message(b)) is False
    finally:
        await w.engine.dispose()
    assert owner_sql(migrated_db, "SELECT status FROM receipt_dispatch WHERE booking_id = %s", (b,)) == [("failed",)]
    assert owner_sql(migrated_db, "SELECT * FROM booking WHERE id = %s", (b,)) == before


def test_exactly_one_owner_only_resend_endpoint_and_no_cancel_or_refund():
    eps = json.loads((REPO / "docs" / "03 PRD" / "api" / "contract.json").read_text(encoding="utf-8"))["endpoints"]
    resend = [e for e in eps if e["path"].endswith("/resend-receipt")]
    assert len(resend) == 1 and "user_id equals their own user id" in resend[0]["authorisation_rule"]
    assert [e["path"] for e in eps if "/cancel" in e["path"] or "/refund" in e["path"]] == []


def test_no_delivery_feedback_machinery(migrated_db):
    assert rg(r"sns|bounce|complaint|SetIdentity", "backend/app", ignore_case=True) == []
    assert app_sql(migrated_db, "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND column_name IN "
                                "('email_invalid','email_bounced','email_complained','email_suppressed')") == [(0,)]


def test_nothing_outside_the_model_layer_reads_cancelled_at():
    assert rg(r"cancelled_at", "backend/app/api", "backend/app/domain", "backend/app/workers") == []


def test_no_customer_facing_string_reports_a_failed_receipt():
    strings = ["receipt failed", "could not be sent", "was not sent", "undelivered", "not delivered", "delivery failed", "bounced",
               "is delayed", "still sending"]
    assert [h for s in strings for h in rg(s, "frontend/src", ignore_case=True, fixed=True)] == []

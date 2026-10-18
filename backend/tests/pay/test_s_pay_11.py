"""S-PAY-11 (P-PAY-12): the payment path has no reverse."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import create_app
from tests.conftest import VALID_ENV
from tests.pay.kit import F7, api, clock_at, confirm, cookies, count, hold, owner_sql, user, world7

pytestmark = pytest.mark.anyio
APP = Path(__file__).resolve().parents[2] / "app"
FRONTEND = Path("/frontend/src")
LINE = "This booking cannot be changed, cancelled or refunded."


@pytest.fixture
def world(migrated_db):
    return world7(migrated_db)


def _openapi() -> dict:
    return create_app(Settings(**VALID_ENV)).openapi()


def _lines(root: Path, pattern: str, suffixes=(".py",)) -> list[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    return [f"{p}:{n}:{line.strip()}" for p in root.rglob("*") if p.is_file() and p.suffix in suffixes
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if rx.search(line)]


def test_the_state_set_is_exactly_four_with_no_refunded(world):
    assert owner_sql(world["db"], "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'payment'::regclass "
                                  "AND conname = 'ck_payment__state'") == [
        ("CHECK ((state = ANY (ARRAY['pending'::text, 'authorized'::text, 'captured'::text, 'failed'::text])))",)]


async def test_no_cancel_or_refund_route_exists(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        for path in ("/api/bookings/1/cancel", "/api/bookings/1/refund"):
            r = await c.post(path, cookies=cookies(c, u))
            assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert [p for p in _openapi()["paths"] if re.search("cancel|refund", p)] == []


async def test_status_and_its_timestamp_are_unknown_properties_and_written_once(world):
    db = world["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        h = await hold(c, u, [F7])
        for extra in ({"status": "cancelled"}, {"cancelled_at": "2026-08-14T14:00:00Z"}):
            r = await confirm(c, u, h["hold_token"], body={"hold_token": h["hold_token"], "showtime_id": 7, **extra})
            assert r.status_code == 400 and r.json()["error"]["code"] == "REQUEST_INVALID"
        ok = await confirm(c, u, h["hold_token"])
    b = ok.json()["booking_id"]
    assert sorted(x[0] for x in owner_sql(db, "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                                              "AND table_name='booking' AND column_name IN ('status','cancelled_at')")) == ["cancelled_at", "status"]
    assert owner_sql(db, "SELECT status FROM booking WHERE id = %s", (b,)) == [("confirmed",)]
    assert count(db, "SELECT count(*) FROM booking WHERE cancelled_at IS NOT NULL") == 0
    schema_text = str(_openapi())
    assert "cancelled_at" not in schema_text


def test_nothing_outside_the_models_writes_status_or_names_the_timestamp():
    hits = [h for h in _lines(APP, r"UPDATE booking SET|cancelled_at") if "/models/" not in h]
    assert hits == []


def test_refund_is_named_once_in_the_receipt_template_and_once_on_the_booking_page():
    backend = _lines(APP, "refund")
    assert len(backend) == 1 and "This booking is final. There is no cancellation and no refund." in backend[0], backend
    front = _lines(FRONTEND, "refund", (".ts", ".tsx"))
    assert len(front) == 1 and LINE in front[0], front


def test_no_route_can_withdraw_a_showtime():
    hits = _lines(APP, "withdraw")
    allowed = {"language.withdrawn", "certification.withdrawn", "genre.withdrawn", "format.withdrawn"}
    assert hits and all(any(a in h for a in allowed) for h in hits), hits
    assert not [h for h in hits if re.search("showtime", h, re.IGNORECASE)]
    deletes = [p for p, ops in _openapi()["paths"].items() if p.startswith("/api/admin/showtimes") and "delete" in ops]
    assert deletes == []

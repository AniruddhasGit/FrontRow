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
    # The amended cell: frontend/src hits only on lines carrying the SCR-TKT-01 sentence, or a published E6 admin
    # withdrawal confirmation containing "nothing is refunded" (SCR-ADM-05, and SCR-ADM-02's film withdraw), the
    # SCR-TKT-01 sentence among them. "Published" is checked: the quoted sentence is in the E6 section verbatim.
    e6 = (Path("/docs/03 PRD/sections/E6_admin.md")).read_text(encoding="utf-8")
    front = _lines(FRONTEND, "refund", (".ts", ".tsx"))
    quoted = [re.search(r'"([^"]*refund[^"]*)"', h, re.IGNORECASE) for h in front]
    assert all(quoted), front
    sentences = [m[1] for m in quoted]
    assert LINE in sentences, front
    assert all(s == LINE or ("nothing is refunded" in s and s in e6) for s in sentences), front


def _walk_names(schema, out: list[str], spec: dict, seen=None) -> list[str]:
    """Every property name reachable from a schema, following $ref into components."""
    seen = set() if seen is None else seen
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if ref and ref not in seen:
            seen.add(ref)
            _walk_names(spec["components"]["schemas"][ref.rsplit("/", 1)[1]], out, spec, seen)
        out += list(schema.get("properties", {}))
        for v in schema.values():
            _walk_names(v, out, spec, seen)
    elif isinstance(schema, list):
        for v in schema:
            _walk_names(v, out, spec, seen)
    return out


def test_no_route_can_withdraw_a_showtime():
    # Every route path, function name and request-schema field containing withdraw concerns a film or a lookup entry.
    app = create_app(Settings(**VALID_ENV))
    film_or_lookup = re.compile(r"movie|film|lookup|language|certification|genre|format", re.I)

    def leaves(routes):  # FastAPI 0.143 nests each included router's routes (see tests/xct/_support.mounted_routes)
        for r in routes:
            nested = []
            for attr in ("effective_candidates", "effective_low_priority_routes"):
                found = getattr(r, attr, ())
                nested.extend(found() if callable(found) else found)
            yield from leaves(nested) if nested else (r,)

    routes = [r for r in leaves(app.routes) if hasattr(r, "path")]  # an included router with no routes has none
    assert any(r.path.startswith("/api/admin/movies") for r in routes)  # not vacuous
    for r in routes:
        name = getattr(getattr(r, "endpoint", None), "__name__", "")
        for label in (r.path, name):
            assert "withdraw" not in label.lower() or film_or_lookup.search(f"{r.path} {name}"), (r.path, name)
    spec = app.openapi()
    for path, ops in spec["paths"].items():
        for op in ops.values():
            fields = [p["name"] for p in op.get("parameters", [])] + _walk_names(op.get("requestBody", {}), [], spec)
            assert not [f for f in fields if "withdraw" in f.lower() and not film_or_lookup.search(f"{path} {f}")], path
    # No DELETE, and no withdraw or cancel operation, on any path beginning /api/admin/showtimes.
    shows = {p: ops for p, ops in spec["paths"].items() if p.startswith("/api/admin/showtimes")}
    assert shows and not [p for p, ops in shows.items() if "delete" in ops or re.search("withdraw|cancel", p, re.I)]
    # rg -in 'withdraw' backend/app: no hit on a line that also matches showtime. Judged on the line's own text, not
    # its file path (a hit in api/admin/showtimes.py is not a line naming showtime). Checked last, so the route and
    # schema clauses above are proved even while this one is red on an honest docstring (see the ledger note).
    hits = _lines(APP, "withdraw")
    on_showtime = [h for h in hits if re.search("showtime", h.split(":", 2)[2], re.IGNORECASE)]
    assert hits and not on_showtime, on_showtime

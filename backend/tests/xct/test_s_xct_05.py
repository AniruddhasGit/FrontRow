"""S-XCT-05 - compute and store every money value as integer paise through one function.

Covered here: boot validation of the currency pair, the money-column census, the one pricing function
and its half-up rule with the PRD's worked examples (P-PAY-03 / P-PAY-04 / FR-ADR-038), the strict
paise boundary type that refuses 250.00 / -1 / 0, the single-formula scan, the five importing files, the
real POST /api/admin/showtimes and PATCH /api/admin/showtimes/41 refusing 250.00, -1 and 0 with 422
VALIDATION_FAILED and storing nothing, and SUM cast back to int.

NOT passing as written: `rg -nP 'float\(|:\s*float|->\s*float' backend/app` returning 0 hits. About ten
non-money duration and metrics annotations hit it (core/config.py, clock.py, metrics.py, server.py,
workers/queue.py); the sweep here covers the money modules only. That clause needs a Bible amendment.
"""

from __future__ import annotations

import ast
import inspect
import re
from decimal import Decimal

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.core.config import ConfigError, load_settings
from app.domain import pricing
from app.domain.money import Paise, PositivePaise
from app.domain.pricing import seat_price_paise
from tests.dbkit import BACKEND_DIR, insert_booking, insert_showtime, insert_user, owner_sql

APP = BACKEND_DIR / "app"


# ---- boot ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["INR", "USD"])  # USD is the ruled currency (SRC-006 CUR-1)
def test_inr_or_usd_with_ratio_100_loads(valid_env, code):
    valid_env.setenv("CURRENCY_CODE", code)
    valid_env.setenv("CURRENCY_MINOR_UNIT_RATIO", "100")
    s = load_settings()
    assert (s.CURRENCY_CODE, s.CURRENCY_MINOR_UNIT_RATIO) == (code, 100)


@pytest.mark.parametrize("code", ["INR", "USD"])
@pytest.mark.parametrize("ratio", ["1000", "10", "1"])
def test_any_other_ratio_with_inr_or_usd_refuses_to_boot_naming_the_variable(valid_env, ratio, code):
    valid_env.setenv("CURRENCY_CODE", code)
    valid_env.setenv("CURRENCY_MINOR_UNIT_RATIO", ratio)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "CURRENCY_MINOR_UNIT_RATIO" in exc.value.names


def test_currency_is_in_the_one_resolved_configuration_line():
    """The once-per-boot line is app/server.py's "configuration resolved" (S-XCT-29's lane); it carries
    every setting, so the currency pair is in it, unredacted."""
    from app.core.config import redacted

    from tests.conftest import VALID_ENV
    from app.core.config import Settings

    shown = redacted(Settings(**VALID_ENV))
    assert shown["CURRENCY_CODE"] == "USD" and shown["CURRENCY_MINOR_UNIT_RATIO"] == 100


# ---- the column census ----------------------------------------------------------------------------------


def test_every_price_amount_total_column_is_bigint_and_named_paise(migrated_db):
    rows = owner_sql(
        migrated_db,
        r"""SELECT table_name, column_name, data_type FROM information_schema.columns
             WHERE table_schema = 'public' AND column_name ~ '(price|amount|total)'
               AND (data_type <> 'bigint' OR column_name !~ '_paise(_applied)?$')""",
    )
    assert rows == []
    # Not vacuous: the money columns are there and visible to this query.
    assert len(owner_sql(migrated_db, "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND column_name ~ '_paise(_applied)?$'")) >= 5


# ---- the one function -----------------------------------------------------------------------------------


def test_pricing_module_defines_exactly_one_public_function_with_the_published_signature():
    tree = ast.parse(inspect.getsource(pricing))
    public = [n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and not n.name.startswith("_")]
    assert public == ["seat_price_paise"]
    sig = inspect.signature(seat_price_paise)
    assert str(sig) == "(base_price_paise: int, uplift_basis_points: int) -> int"


def test_the_fixture_rounds_half_up_and_three_seats_total_99999_never_99998():
    # 25000 * (10000 + 3333) / 10000 = 33332.5 exactly -> half-up 33333 (half-even would give 33332).
    assert seat_price_paise(25000, 3333) == 33333
    seats = [seat_price_paise(25000, 3333) for _ in range(3)]
    total = sum(seats)  # the total is the sum of rounded seats and is never itself rounded
    assert total == 99999
    assert total != 99998


@pytest.mark.parametrize(
    "base,uplift,expected",
    [(27500, 1250, 30938), (27500, 3333, 36666), (27500, 0, 27500)],  # P-PAY-03 worked example
)
def test_prd_worked_examples(base, uplift, expected):
    assert seat_price_paise(base, uplift) == expected


def test_prd_five_seat_total_is_166146_not_166144():
    total = 3 * seat_price_paise(27500, 1250) + 2 * seat_price_paise(27500, 3333)
    assert total == 166146  # P-PAY-04; rounding the exact sum once would give 166144


@pytest.mark.parametrize("bad", [25000.0, Decimal("25000"), "25000", True])
def test_a_non_int_argument_is_a_type_error_not_a_rounded_result(bad):
    with pytest.raises(TypeError):
        seat_price_paise(bad, 0)
    with pytest.raises(TypeError):
        seat_price_paise(25000, bad)


@pytest.mark.parametrize("base,uplift", [(-1, 0), (25000, -1)])
def test_negative_inputs_are_refused(base, uplift):
    with pytest.raises(ValueError):
        seat_price_paise(base, uplift)


def test_the_formula_is_written_once_uplift_appears_nowhere_else_in_app():
    r"""CR-002 A-10 (2): rg -nP 'uplift_basis_points\w*\s*[-+*/%]|[-+*/%]\s*uplift_basis_points' backend/app scripts
    --glob '!**/domain/pricing.py' returns 0 hits. Reading, storing and validating the column stays allowed."""
    from tests.xct._support import rg

    hits = rg(r"uplift_basis_points\w*\s*[-+*/%]|[-+*/%]\s*uplift_basis_points", "backend/app", "scripts")
    assert [f"{h[0]}:{h[1]}" for h in hits if h[0] != "backend/app/domain/pricing.py"] == []
    rx = re.compile(r"uplift_basis_points\w*\s*[-+*/%]|[-+*/%]\s*uplift_basis_points")
    assert rx.search("base * uplift_basis_points") and rx.search("uplift_basis_points_applied % 7")
    assert not rx.search('row["uplift_basis_points"]') and not rx.search("uplift_basis_points=Column(BigInteger)")


def test_only_the_five_real_importers_use_pricing_and_the_receipt_and_reports_do_not():
    """CR-002 A-10 (3): the seat-map read, the hold snapshot, the booking total, the admin base-price bound and
    scripts/seed.py import app.domain.pricing; the receipt render and the reporting domain import nothing from it."""
    from tests.xct._support import rg

    files = {h[0] for h in rg(r"from app\.domain\.pricing import", "backend/app", "scripts")}
    assert files <= {"backend/app/domain/browse/seatmap.py", "backend/app/domain/holds/__init__.py",
                     "backend/app/domain/booking/__init__.py", "backend/app/domain/admin/common.py", "scripts/seed.py"}, files
    assert rg(r"app\.domain\.pricing|app\.domain import pricing", "backend/app/workers/render.py", "backend/app/domain/reports") == []
    # They read stored paise, never a recomputed price: the reports sum booking_seat.price_paise, and the receipt's
    # one read (RECEIPT_FACTS) takes booking.total_paise, the confirm-time sum of booking_seat.price_paise (S-PAY-07).
    from app.workers import RECEIPT_FACTS

    assert "b.total_paise" in str(RECEIPT_FACTS) and "seat_price_paise" not in (APP / "workers" / "render.py").read_text()
    assert rg(r"SUM\(bs\.price_paise\)", "backend/app/domain/reports")


# ---- the request boundary: integer paise, or 422 ---------------------------------------------------------


@pytest.mark.parametrize("bad", [250.00, -1, 0, "25000", True])
def test_positive_paise_refuses_a_float_negative_zero_string_or_bool_and_never_rounds(bad):
    with pytest.raises(ValidationError):
        TypeAdapter(PositivePaise).validate_json(__import__("json").dumps(bad))


def test_positive_paise_accepts_an_integer_and_paise_accepts_zero():
    assert TypeAdapter(PositivePaise).validate_json("25000") == 25000
    assert TypeAdapter(Paise).validate_json("0") == 0


def test_a_json_250_00_body_field_is_422_validation_failed_through_the_product_envelope():
    """The admin showtime endpoint is another lane's; this proves the mechanism it will use: a
    PositivePaise body field plus the global handler turns 250.00 into 422 VALIDATION_FAILED."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.errors import install_error_handlers

    probe = FastAPI()
    install_error_handlers(probe)

    @probe.post("/probe")
    async def handler(body: Body) -> dict:
        return {"base_price_paise": body.base_price_paise}

    client = TestClient(probe)
    for bad in ("250.00", "-1", "0"):
        r = client.post("/probe", content='{"base_price_paise": %s}' % bad, headers={"content-type": "application/json"})
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "VALIDATION_FAILED"
        assert r.json()["error"]["details"] == {"field": "base_price_paise"}
    assert client.post("/probe", json={"base_price_paise": 25000}).json() == {"base_price_paise": 25000}


class Body(BaseModel):
    base_price_paise: PositivePaise


def test_the_real_showtime_endpoints_refuse_250_00_minus_1_and_0_and_store_nothing(migrated_db, clock):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.adm.kit import make_movie, make_screen, make_seats, sign_in
    from tests.dbkit import app_settings
    from tests.test_health import ok_probe

    app = create_app(app_settings(migrated_db), clock=clock, probes=[ok_probe("postgres"), ok_probe("redis")])
    with TestClient(app, raise_server_exceptions=False) as c:
        c.clock, c.db = clock, migrated_db
        sign_in(c)
        hall, movie = make_screen(migrated_db), make_movie(migrated_db)
        make_seats(migrated_db, hall, 1)
        owner_sql(migrated_db, "INSERT INTO showtime (id, movie_id, screen_id, starts_at, ends_at, base_price_paise, "
                               "seat_count_at_creation, version) OVERRIDING SYSTEM VALUE VALUES (41, %s, %s, "
                               "'2026-12-01T12:30:00Z', '2026-12-01T15:00:00Z', 25000, 1, 1)", (movie, hall))
        before = owner_sql(migrated_db, "SELECT count(*), sum(base_price_paise) FROM showtime")
        fields = (f'"movie_id": {movie}, "screen_id": {hall}, '
                  '"starts_at": "2026-09-01T18:00:00", "ends_at": "2026-09-01T20:30:00"')
        for bad in ("250.00", "-1", "0"):
            for method, url, body in (("POST", "/api/admin/showtimes", "{" + fields + ', "base_price_paise": ' + bad + "}"),
                                      ("PATCH", "/api/admin/showtimes/41", '{"base_price_paise": ' + bad + "}")):
                r = c.request(method, url, content=body, headers={"content-type": "application/json"})
                assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_FAILED"), (method, bad, r.text)
        assert owner_sql(migrated_db, "SELECT count(*), sum(base_price_paise) FROM showtime") == before  # never rounded


# ---- SUM over bigint comes back as int, never Decimal -----------------------------------------------------


@pytest.mark.anyio
async def test_sum_of_price_paise_cast_to_bigint_arrives_as_int(migrated_db):
    from sqlalchemy import BigInteger, cast, func, select
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db import async_url
    from app.models import booking_seat

    st = insert_showtime(migrated_db)
    insert_booking(migrated_db, user_id=insert_user(migrated_db, role="customer"), showtime=st, price_paise=33333, reference="CAFE2345")
    engine = create_async_engine(async_url(migrated_db.app_url))
    try:
        async with engine.connect() as conn:
            raw = (await conn.execute(select(func.sum(booking_seat.c.price_paise)))).scalar_one()
            value = (await conn.execute(select(cast(func.sum(booking_seat.c.price_paise), BigInteger)))).scalar_one()
    finally:
        await engine.dispose()
    assert isinstance(raw, Decimal)  # the trap, observed: PostgreSQL SUM(bigint) is numeric
    assert isinstance(value, int) and not isinstance(value, Decimal)
    assert value == 33333


def test_no_float_annotation_or_call_on_the_money_modules():
    """The money path itself carries no float. (The criterion's repo-wide rg also matches Phase 1's
    duration annotations - see the lane report.)"""
    rx = re.compile(r"float\(|:\s*float|->\s*float")
    for module in ("domain/pricing.py", "domain/money.py", "core/audit.py"):
        assert not rx.search((APP / module).read_text(encoding="utf-8")), module

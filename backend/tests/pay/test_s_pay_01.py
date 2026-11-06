"""S-PAY-01 - every money value is held as integer paise.

Covered: boot with the ratio unset / 0 / non-integer (exits non-zero before binding, names the
variable), the four money columns on booking / booking_seat / payment, no float or Decimal in the
pricing module, no currency sign in the API and domain layers, one assignment of the ratio name, no
literal-100 arithmetic in pricing. NOT covered: POST /api/bookings (EP-PAY-01, Phase 4) and its 201
body, and the two files that do not exist yet (api/bookings.py, domain/payment/).
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys

import pytest

from app.core.config import ConfigError, load_settings
from tests.conftest import VALID_ENV
from tests.dbkit import BACKEND_DIR, app_sql

APP = BACKEND_DIR / "app"


def test_usd_with_ratio_100_boots(valid_env):
    valid_env.setenv("CURRENCY_MINOR_UNIT_RATIO", "100")
    s = load_settings()
    assert (s.CURRENCY_CODE, s.CURRENCY_MINOR_UNIT_RATIO) == ("USD", 100)


@pytest.mark.parametrize("ratio", ["0", "1.5", "abc"])
def test_a_zero_or_non_integer_ratio_is_refused_naming_it(valid_env, ratio):
    valid_env.setenv("CURRENCY_MINOR_UNIT_RATIO", ratio)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "CURRENCY_MINOR_UNIT_RATIO" in exc.value.names


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_an_unset_ratio_boots_with_the_s7_9_default_of_100(valid_env):
    """S-PAY-01 as amended: 'with CURRENCY_MINOR_UNIT_RATIO unset it boots with the S7.9 default of 100'. An invalid
    value is still refused (test_a_zero_or_non_integer_ratio_is_refused_naming_it)."""
    valid_env.delenv("CURRENCY_MINOR_UNIT_RATIO", raising=False)
    assert load_settings().CURRENCY_MINOR_UNIT_RATIO == 100


@pytest.mark.parametrize("ratio", ["0", "1.5"])
def test_the_process_exits_before_binding_and_stderr_names_the_variable(tmp_path, ratio):
    port = _free_port()
    env = {**os.environ, **VALID_ENV, "CURRENCY_MINOR_UNIT_RATIO": ratio, "API_PORT": str(port), "PYTHONPATH": str(BACKEND_DIR)}
    proc = subprocess.run([sys.executable, "-m", "app", "api"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0
    assert "CURRENCY_MINOR_UNIT_RATIO" in proc.stderr
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()


def test_the_money_columns_are_exactly_four_and_all_bigint(migrated_db):
    rows = app_sql(migrated_db, "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' "
                                "AND table_name IN ('booking','booking_seat','payment') AND column_name LIKE '%paise%'")
    assert sorted(rows) == sorted([("total_paise", "bigint"), ("price_paise", "bigint"),
                                   ("base_price_paise_applied", "bigint"), ("amount_paise", "bigint")])


def test_pricing_holds_no_float_or_decimal():
    for path in (APP / "domain" / "pricing.py", APP / "api" / "bookings.py"):
        assert not re.search(r"float\(|Decimal", path.read_text(encoding="utf-8")), path


def test_the_api_and_domain_layers_format_no_money():
    hits = [str(p) for d in ("api", "domain") for p in (APP / d).rglob("*.py") if re.search(r"₹|\$\{|\$\d", p.read_text(encoding="utf-8"))]
    assert hits == []


def test_the_ratio_is_assigned_exactly_once_in_the_settings_module():
    assign = re.compile(r"^\s*CURRENCY_MINOR_UNIT_RATIO\s*[:=]")
    hits = [
        (p.relative_to(BACKEND_DIR).as_posix(), line.strip())
        for p in APP.rglob("*.py")
        for line in p.read_text(encoding="utf-8").splitlines()
        if assign.search(line)
    ]
    assert len(hits) == 1 and hits[0][0] == "app/core/config.py", hits


def test_pricing_never_multiplies_or_divides_by_a_literal_100():
    paths = [APP / "domain" / "pricing.py", APP / "api" / "bookings.py", *(APP / "domain" / "payment").rglob("*.py")]
    for path in paths:
        assert not re.search(r"[*/]\s*100\b|\b100\s*[*/]", path.read_text(encoding="utf-8")), path


@pytest.mark.anyio
async def test_the_201_body_carries_integer_paise_and_no_formatted_money(migrated_db):
    """The five-seat fixture of S-PAY-02 (base $275.00 = 27500 cents; $1,661.46 = 166146 cents): every
    money value in the 201 is a JSON integer, no formatted or ambiguous money key exists, and no currency sign is sent."""
    from tests.pay.kit import FIVE, api, clock_at, confirm, hold, owner_sql, user, world7

    db = world7(migrated_db)["db"]
    u = user(db)
    async with api(db, clock_at()) as c:
        r = await confirm(c, u, (await hold(c, u, FIVE))["hold_token"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert type(body["total_paise"]) is int and body["total_paise"] == 166146 and '"total_paise":166146' in r.text
    for seat in body["seats"]:
        assert type(seat["price_paise"]) is int and type(seat["base_price_paise_applied"]) is int
        assert seat["base_price_paise_applied"] == 27500
    assert not {"total", "amount", "price", "total_formatted", "currency_display"} & set(body)
    assert "$" not in r.text and "₹" not in r.text and "\\u20b9" not in r.text
    assert owner_sql(db, "SELECT total_paise FROM booking") == [(166146,)]

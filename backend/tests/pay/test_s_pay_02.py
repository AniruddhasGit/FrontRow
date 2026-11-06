"""S-PAY-02 (P-PAY-03, P-PAY-04, FR-ADR-038): one integer half-up function prices every seat, and a total is the
plain sum of already-rounded seat prices.

The figures are literals from the criterion. The category names and uplifts behind them are ASSUMED
(OPEN-SEAT-01) and illustrative only, so this module reads nothing from any stored catalogue.
"""

from __future__ import annotations

import re

import pytest

from app.domain.pricing import BASIS_POINTS_DENOMINATOR, ROUNDING_HALF_NUMERATOR, seat_price_paise
from tests.xct._support import REPO, rg


@pytest.mark.parametrize("base,uplift,expected", [
    (27500, 1250, 30938),  # 3437.5 rounds up to 3438
    (27500, 3333, 36666),  # 9165.75 rounds to 9166
    (27500, 0, 27500),
    (25000, 3333, 33333),  # 8332.5 rounds up; half-even would give 33332
])
def test_the_worked_prices(base, uplift, expected):
    assert seat_price_paise(base, uplift) == expected


@pytest.mark.parametrize("args", [(27500.0, 1250), (27500, 1250.0), (True, 1250)])
def test_a_non_integer_is_a_type_error_and_never_rounded(args):
    with pytest.raises(TypeError):
        seat_price_paise(*args)


@pytest.mark.parametrize("args", [(-1, 1250), (27500, -1)])
def test_a_negative_is_a_value_error(args):
    with pytest.raises(ValueError):
        seat_price_paise(*args)


def test_the_total_is_the_sum_of_rounded_seat_prices_and_is_never_rounded_again():
    prices = [seat_price_paise(27500, 1250)] * 3 + [seat_price_paise(27500, 3333)] * 2
    total = sum(prices)
    assert total == 3 * 30938 + 2 * 36666 == 166146
    assert total != 166144  # carrying exact values and rounding once: 3 x 30937.5 + 2 x 36665.75


def test_the_constants_are_named_once():
    assert (BASIS_POINTS_DENOMINATOR, ROUNDING_HALF_NUMERATOR) == (10_000, 5_000)
    hits = rg(r"BASIS_POINTS_DENOMINATOR|ROUNDING_HALF_NUMERATOR", "backend/app")
    definitions = [h for h in hits if re.match(r"^(BASIS_POINTS_DENOMINATOR|ROUNDING_HALF_NUMERATOR)\s*=", h[2])]
    assert {h[0] for h in hits} == {"backend/app/domain/pricing.py"} and len(definitions) == 2


def test_exactly_one_implementation_of_the_formula():
    defs = rg(r"def seat_price_paise", "backend/app", "backend/migrations")
    assert [h[0] for h in defs] == ["backend/app/domain/pricing.py"]


# CR-002 A-1: a hit is excused only when it is a whole-line assignment of a named duration constant (*_MS, *_SECONDS).
DURATION_CONSTANT = re.compile(r"^\s*[A-Z][A-Z0-9_]*_(MS|SECONDS)\s*=\s*\d+\s*(#.*)?$")


def test_no_literal_denominator_or_half_outside_pricing():
    hits = rg(r"\b10000\b|\b5000\b", "backend/app/domain", "backend/app/api", "backend/app/workers")
    hits = [h for h in hits if not h[0].endswith("/pricing.py")]
    assert [h for h in hits if not DURATION_CONSTANT.match(h[2])] == []


def test_the_duration_excuse_takes_no_arithmetic():
    assert DURATION_CONSTANT.match("MUTEX_TTL_MS = 5000  # five seconds")
    for line in ("MUTEX_TTL_MS = 5 * 1000", "price = base * u // 10000", "HALF = 5000", "X_MS = base + 5000"):
        assert not DURATION_CONSTANT.match(line), line


def test_no_caller_does_its_own_uplift_arithmetic():
    hits = rg(r"uplift_basis_points\s*[-+*/]|[-+*/]\s*uplift_basis_points", "backend/app")
    assert [h for h in hits if not h[0].endswith("/pricing.py")] == []


def test_no_other_function_is_named_for_a_price_in_paise():
    # RED while app/domain/admin/common.py (the admin lane's) declares check_ceiling(base_price_paise, ...).
    hits = rg(r"def .*price.*paise", "backend/app")
    assert [h for h in hits if not h[0].endswith("/pricing.py")] == []


def test_this_module_reads_no_stored_data():
    words = "|".join(["se" + "ed", "ses" + "sion", "db" + "_", r"cli" + r"ent\."])
    source = (REPO / "backend" / "tests" / "pay" / "test_s_pay_02.py").read_text(encoding="utf-8")
    assert re.search(words, source) is None

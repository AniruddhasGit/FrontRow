"""S-PAY-04 (P-PAY-07): refuse to boot on a payment configuration that could break a confirm.

Most clauses are rules of app/core/config.py (Zone B, the config lane's file); this module asserts them where they
already hold and fails, by design, on the ones that do not (see the lane report)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import ConfigError, load_settings

APP = Path(__file__).resolve().parents[2] / "app"


def _boots(env, **values) -> bool:
    for k, v in values.items():
        if v is None:
            env.delenv(k, raising=False)
        else:
            env.setenv(k, v)
    try:
        load_settings()
        return True
    except ConfigError:
        return False


def _refusal(env, **values) -> ConfigError:
    for k, v in values.items():
        if v is None:
            env.delenv(k, raising=False)
        else:
            env.setenv(k, v)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    return exc.value


@pytest.mark.parametrize("ttl,ok,refused", [("180", ["1500", "17999"], ["18000", "60000"]), ("60", ["5999"], ["6000"])])
def test_the_delay_bound_is_a_tenth_of_the_hold(valid_env, ttl, ok, refused):
    for v in ok:
        assert _boots(valid_env, SEAT_HOLD_TTL_SECONDS=ttl, PAYMENT_SIMULATED_DELAY_MS=v), v
    for v in refused:
        assert not _boots(valid_env, SEAT_HOLD_TTL_SECONDS=ttl, PAYMENT_SIMULATED_DELAY_MS=v), v


def test_the_refusal_names_the_variable_the_value_and_the_computed_bound(valid_env):
    err = _refusal(valid_env, SEAT_HOLD_TTL_SECONDS="180", PAYMENT_SIMULATED_DELAY_MS="18000")
    text = str(err)
    assert "PAYMENT_SIMULATED_DELAY_MS" in text and "18000" in text.replace("18,000", "18000")
    # The configured value AND the bound must both be named; at 18000 they coincide, so check 60000 too.
    text = str(_refusal(valid_env, SEAT_HOLD_TTL_SECONDS="180", PAYMENT_SIMULATED_DELAY_MS="60000"))
    assert "60000" in text and "18000" in text


def test_a_zero_delay_is_refused(valid_env):
    assert not _boots(valid_env, PAYMENT_SIMULATED_DELAY_MS="0")


def test_the_provider_has_no_default_and_no_other_value(valid_env):
    assert not _boots(valid_env, PAYMENT_PROVIDER=None)
    err = _refusal(valid_env, PAYMENT_PROVIDER="stripe")
    assert "PAYMENT_PROVIDER" in err.names and re.search(r"no other provider|only permitted", str(err))


@pytest.mark.parametrize("prefix", ["a", "deadbeef"])
def test_a_prefix_drawn_from_the_uuid_alphabet_is_refused(valid_env, prefix):
    err = _refusal(valid_env, PAYMENT_SIMULATOR_FAIL_KEY_PREFIX=prefix)
    assert "PAYMENT_SIMULATOR_FAIL_KEY_PREFIX" in str(err) and prefix in str(err)


def test_the_prefix_bounds(valid_env):
    assert _boots(valid_env, PAYMENT_SIMULATOR_FAIL_KEY_PREFIX="FAIL_")
    assert not _boots(valid_env, PAYMENT_SIMULATOR_FAIL_KEY_PREFIX=None)
    assert not _boots(valid_env, PAYMENT_SIMULATOR_FAIL_KEY_PREFIX="F" * 33)


def test_the_assumed_values_appear_only_in_the_settings_module():
    pattern = re.compile(r"\b1500\b|FAIL_")
    hits = [f"{p.relative_to(APP)}:{n}" for p in APP.rglob("*.py") if p.name not in ("config.py", "settings.py")
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert hits == []

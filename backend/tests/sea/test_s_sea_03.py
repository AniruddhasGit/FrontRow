"""S-SEA-03 (P-SEA-04): the seat object carries its already-rounded price_paise and no uplift field at all, so the
client sums integers and performs no arithmetic.

The running total itself (the five renders, 156249 not 156248, the formatter, the line count) is the client's and
is unit-tested in frontend/src/features/seatmap/model.test.mjs. Not here (browser harness): the rendered panel,
the disabled primary action, the regex sweep of the rendered region.
"""

from __future__ import annotations

import pytest

from app.domain.browse.seatmap import Seat
from tests.scp.test_s_scp_08 import _contract_seat_keys

SEAT_KEYS = {"id", "row", "num", "gr", "gc", "cat", "price_paise", "state", "is_active"}


def test_the_contract_seat_object_is_exactly_these_properties():
    assert _contract_seat_keys() == SEAT_KEYS


def test_the_response_model_is_exactly_these_properties_and_carries_no_uplift():
    assert set(Seat.model_fields) == SEAT_KEYS
    assert not [k for k in Seat.model_fields if "uplift" in k]


@pytest.mark.parametrize("price", [-1, 2.5, "25000", True])
def test_a_price_that_is_not_a_non_negative_integer_is_refused(price):
    with pytest.raises(ValueError):
        Seat(id=1, row="C", num=12, gr=3, gc=12, cat=1, price_paise=price, state="available", is_active=True)

"""S-SCP-11 (P-SCP-05, SRC-001 §6.5): no point-of-sale integration.

Not here, and why the row stays Blocked: the before_insert listener on booking_seat across a run of the booking
confirmation path AND scripts/seed.py - the confirmation path is Phase 4 (EP-PAY-01).
"""

from __future__ import annotations

from tests.xct._support import rg


def test_no_point_of_sale_vocabulary_in_the_application():
    assert rg(r"\bpos\b|\btill\b|counter_?sale|terminal_?sale", "backend/app", "frontend/src", ignore_case=True) == []

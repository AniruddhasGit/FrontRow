# S-PAY-02 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/pay/test_s_pay_02.py passed, all of it including test_no_literal_denominator_or_half_outside_pricing, which was a baseline red. New: tests/pay/test_s_pay_02_total.py::test_the_booking_total_is_166146_never_166144 (POST /api/bookings: total 166146, != 166144; booking.total_paise, payment.amount_paise and sum(booking_seat.price_paise) all 166146).

**Note:** DependsOn not yet Done: S-PAY-01, E-ADM-A. The baseline red was MUTEX_TTL_MS = 5000 in domain/holds; it is now written as 5 * 1000. The product-total test lives in its own module, because the AC forbids the pricing test module from reading stored data.

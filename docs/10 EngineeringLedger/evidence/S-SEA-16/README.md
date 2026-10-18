# S-SEA-16 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/sea/test_s_sea_16.py passed. test_an_admin_price_change_moves_nothing_already_held now confirms at 19:34:20: 201, payment.amount_paise 106665, booking_seat (416,33333,25000),(417,33333,25000),(418,39999,30000), and a pricing-function spy (patched in pricing and holds) records [] during the confirm. New: test_redis_unreachable_at_confirm_is_503_and_nothing_is_charged.

**Note:** DependsOn not yet Done: E-ADM-A. Every clause is now asserted against the product.

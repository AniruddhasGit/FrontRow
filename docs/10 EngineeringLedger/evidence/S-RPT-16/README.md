# S-RPT-16 — Done

Lane `p8-reports`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/rpt/test_s_rpt_16.py (5 tests) green: no rollup or matview; the only Redis key created is the caller's bucket and no key holds takings_paise; the live +25000 shows; the six indexes exist; the payment join is payment.id = booking.payment_id and payment.booking_id does not exist; no metrics use and no reporting import in domain/booking.

**Note:** No migration was needed: all six required indexes already exist from 0001_initial_schema.

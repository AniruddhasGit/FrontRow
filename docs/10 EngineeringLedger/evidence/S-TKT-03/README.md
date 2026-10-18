# S-TKT-03 — Done

Lane `p5-mail`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/tkt/test_s_tkt_03.py: 3 passed (exactly 8 keys; starts_at 2026-08-21T19:15:00+05:30; seats [F7,F8,F9] from rows inserted F9,F7,F8; total_paise 84372 still returned after base_price is changed; admin non-owner 404 equals the unknown-reference 404; with dependency_overrides[owned_reference]=pass-through the admin gets 200).

**Note:** Ownership lives only in the router dependency owned_reference. The handlers re-normalise the reference but carry no owner check.

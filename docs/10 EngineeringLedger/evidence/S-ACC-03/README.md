# S-ACC-03 — Done

Lane `p2-accounts`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_03.py, 10 PASS: test_sign_in_in_any_case_returns_200_and_writes_only_last_signed_in_at (200, cookie, body; last_signed_in_at equals the injected instant; email/password_hash/role/password_version/created_at identical before and after; 0 audit rows), test_unknown_address_and_wrong_password_are_identical_but_for_the_request_id (same status, Content-Type, key set and body once request_id is removed; request_ids differ; exact message; last_signed_in_at stays NULL), test_a_missing_or_empty_field_is_422 x6 ('Enter your email address and password.'), test_a_ten_character_stored_password_still_signs_in, test_nine_failures_lock_nothing_and_the_tenth_attempt_signs_in (9 x 401, role unchanged, exactly the seven columns, 10th attempt 200).


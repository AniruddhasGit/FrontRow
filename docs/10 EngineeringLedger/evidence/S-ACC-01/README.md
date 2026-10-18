# S-ACC-01 — Done

Lane `p2-accounts`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_01.py, 6 PASS: test_register_returns_201_sets_the_session_and_stores_one_customer_row (201, fr_session set, body exactly {user_id,email:'Ada@Example.com',role:'customer'}, one row with role customer / password_version 1 / last_signed_in_at NULL, hash != password, 'correct horse battery' absent from the body, from the DEBUG log stream plus captured stdout for the whole request, and from users::text), test_the_users_table_has_exactly_the_seven_columns, test_a_second_registration_in_another_case_is_409 (409 EMAIL_ALREADY_REGISTERED with the exact sentence), test_twenty_simultaneous_identical_registrations_make_one_account (RATE_LIMIT_REGISTER_IP_PER_HOUR=25: [201]+[409]*19, no RATE_LIMITED, no 5xx, count 1), test_the_bucket_is_still_counting_during_the_larger_bucket_run (the 26th request is 429, so the limiter was live during that run), test_role_is_never_read_from_the_request_body. Lane run: 66 passed, 4 failed in 41.50s. None of the 4 is in this file.

**Note:** Reused the existing 0001 migration, which already holds the users table and uq_users__email_ci. A simultaneous twin's unique violation is caught by constraint name and becomes 409.

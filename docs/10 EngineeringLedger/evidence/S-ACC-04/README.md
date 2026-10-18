# S-ACC-04 — Done

Lane `p2-accounts`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_04.py, 15 PASS: test_the_cookie_attributes_with_secure_from_configuration[false/true] (exactly HttpOnly, SameSite lax, Path=/, Max-Age=43200, Secure iff COOKIE_SECURE=true), test_the_process_refuses_to_start_without_the_variable_and_names_it_on_stderr[COOKIE_SECURE/JWT_SECRET] (subprocess `python -m app api`, non-zero exit, name present in stderr), test_the_token_carries_exactly_five_claims_and_no_email, test_a_password_version_behind_the_row_is_refused, test_a_removed_user_row_is_refused ('Sign in to continue.'), test_a_token_missing_one_claim_is_refused_not_defaulted[sub/role/pv/iat/exp] (five separate 401 AUTH_REQUIRED), test_a_role_changed_in_the_database_applies_on_the_next_request, test_sign_out_is_204_with_a_matching_clearing_cookie_in_every_state (signed in, no cookie, expired, malformed, second call: each 204 with 'fr_session=;' + Max-Age=0 and the issued attributes), test_no_session_table_exists.

**Note:** Required foundation edits in security.py: all five claims are now required, and the clearing cookie is written as 'fr_session=;'. Starlette renders an empty value as "". SameSite is emitted as 'lax' and asserted case-insensitively.

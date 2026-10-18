# S-ACC-05 — Done

Lane `p2-accounts`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_05.py, 7 PASS: test_the_lifetime_is_twelve_hours_on_the_injected_clock (clock at 2026-08-14T10:00:00Z gives iat 10:00:00Z, exp 22:00:00Z and Max-Age=43200; 21:59:00Z is 200; 22:00:01Z is 401 'Your session has ended. Sign in to continue.'; the injected clock is two months off the container clock), test_a_zero_or_non_integer_lifetime_fails_startup_naming_the_variable[0/twelve/1.5] (stderr names SESSION_TTL_SECONDS), test_no_refresh_route_exists_in_the_contract_or_the_running_app (no refresh/renew/reissue/exchange/session path in contract.json or the mounted routes; contract token paths are exactly EP-HLD-02/03/04; app token paths are a subset of those), test_43200_appears_once_in_the_codebase_and_only_in_config, test_no_test_in_this_module_reads_a_clock_or_sleeps.

**Note:** Expiry is the app's own exp comparison against the injected clock. verify_exp is off in decode_session_token.

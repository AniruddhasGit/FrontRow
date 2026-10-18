# T-P1-02 — Done

Lane `phase1-close`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_29.py::test_each_of_the_five_unset_exits_nonzero_naming_it_and_never_binds[DATABASE_URL|REDIS_URL|QUEUE_URL|JWT_SECRET|COOKIE_SECURE] passed. Real container, isolated network: `docker run ... -e JWT_SECRET= frontrow-api:p1close` exited 78 and printed {"level":"CRITICAL","logger":"app.boot","message":"configuration invalid, refusing to start: JWT_SECRET is required and is not set (or is set to an empty string)",...,"missing_or_invalid":["JWT_SECRET"]} on both stdout and stderr.

**Note:** No required variable has a default. Asserted by test_the_five_have_no_default, which passed.

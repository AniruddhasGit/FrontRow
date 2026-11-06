# S-TKT-15 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/tkt/test_s_tkt_15.py. Every clause. New: test_the_stubbed_token_rides_only_in_the_message_and_the_link - accounts.new_reset_token stubbed to TESTTOKENVALUE0001, EP-ACC-05 called, the sent body has exactly the five keys with reset_token TESTTOKENVALUE0001, the real Worker handles that message, the recorded email's link line ends token=TESTTOKENVALUE0001, and the token is absent from SELECT payload::text FROM outbox_message, from password_reset_token::text and from the stdout captured at DEBUG for the request AND the worker run.

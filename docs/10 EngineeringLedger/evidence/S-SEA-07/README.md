# S-SEA-07 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/sea/test_s_sea_07.py. Every clause. New: test_an_absent_hold_ttl_boots_with_the_default_of_180 - SEAT_HOLD_TTL_SECONDS deleted from the environment, load_settings() boots with 180 (SRC-008 HOLD-1). The non-integer / <= 0 refusals and the 17999 boots / 18000 exits delay rule were already asserted. One earlier run of this module saw a 429 on the 180 s parametrisation (a shared Redis rate bucket); the two later runs passed.

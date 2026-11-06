# S-SEA-08

## 2026-11-07: Done (CR-002 B-13 built)

**Built:** `backend/app/api/errors.py`: the application's 404 handler answers an unroutable `/api/holds/<43+ chars
spanning more than one segment>` with 400 REQUEST_INVALID and P-HLD-03's sentence, touching no Redis. Published routes
unchanged (Q-R3-05 recommendation).

**Run:** `tests/sea/test_s_sea_08.py`, all 8 tests pass (2026-11-07, rerun alone after a run shared with other
worktrees' pytest hit `tuple concurrently updated` in fixture setup). `test_unmatched_foreign_and_malformed_tokens`
now asserts `A*21 + "/" + A*21` beside 42, 44, `+` and `=`: five times (400, REQUEST_INVALID, the sentence, empty Redis
log). The wall-clock / bounded-sleep sweep over backend/tests passes (CR-002 A-5).

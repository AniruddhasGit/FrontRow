# S-ACC-15 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/booking_run.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Measured 2026-11-07, local stack, 1500 ms simulated payment: 'signed-in: 20 runs; slowest 4 s; median 3 s' / 'first-time: 20 runs; slowest 6 s; median 5 s' / 'expired: 0 of 20 signed-in runs, 0 of 20 first-time runs ended 409 HOLD_EXPIRED'. Script speed (no human think time), as the clause's t0..t1 defines. The local register limit was reset between first-time runs (stated on stderr).

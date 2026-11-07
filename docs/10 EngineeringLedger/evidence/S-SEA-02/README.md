# S-SEA-02 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/browse_seat.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Taps write fr.selection with 0 requests; sold/held/inactive taps change nothing; the eleventh is refused with 'Up to 10 seats.'; reload restores and re-checks; fr.selection deleted when empty or held; fr.pending_selection null; no unload requests; no locks left.

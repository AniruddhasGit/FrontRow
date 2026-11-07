# S-SEA-12 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/browse_seat.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** A real conflicting hold (second account) answers 409; the seat repaints held_by_other in --fr-seat-held-other with the bar, never the sold hatch; the other seat stays chosen.

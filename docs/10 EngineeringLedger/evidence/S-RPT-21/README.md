# S-RPT-21 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/dashboard_admin.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Typed dates and select changes fire no request, only Apply does; options stay byte-identical; a date change that removes both selections clears them with the exact announcement; the follow-up request carries neither filter. Fixed on the way: the change-log filter inputs overlapped at 1440 px (reports.css .rpt-field min-width 0, controls width 100%).

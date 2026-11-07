# S-RPT-18 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/dashboard_admin.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Real clicks leave exactly one aria-selected tab; the hall filter's change event requests &screen_id=3 and the scope line changes; scope and dashboard load together, showtimes after the dashboard.

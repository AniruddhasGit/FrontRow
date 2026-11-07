# S-BRW-12 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/browse_seat.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Inactive cell dashed 1px transparent, ArrowRight focus, no selection on Enter/Space, four glyphs under one colour, change ring on the fake clock and none under reduced motion, at 375 and 1440 px (after the 0.72 zoom on the desktop panel map was removed: it shrank cells to 17px).

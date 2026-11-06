# S-BRW-04 — Done

Clause-gap pass, 2026-11-07. The writer did not verify its own work: no second reviewer was used. That is recorded here.

**Evidence:** backend/tests/brw/test_s_brw_04.py passed 11 of 11, from `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q tests/brw/test_s_brw_04.py`. The new test is test_the_zone_literal_appears_only_on_p_adm_25s_sentence. It runs the amended `rg 'Asia/Kolkata' backend/app/api backend/app/domain backend/app/models` and requires every hit to be a line carrying P-ADM-25's sentence. Today the only hit is app/domain/admin/cinemas.py ZONE_BAD. That test replaces the earlier lane-only sweep. The existing tests cover these clauses:
- one showtime satisfying every filter;
- the local-day predicate in Kolkata and in Dubai;
- 23:45 included and 00:10 excluded;
- the malformed filters returning 422 with their sentences;
- 999999 returning an empty 200;
- page=2 returning byte-identical output.

The 'Nothing is showing for the chosen filters.' empty state and its 'Clear filters' control are asserted in frontend/src/features/browse/render.test.mjs.

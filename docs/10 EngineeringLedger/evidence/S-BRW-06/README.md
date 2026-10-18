# S-BRW-06 — Done

Lane `render-harness`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** render.test.mjs, three S-BRW-06 tests ✔ (7 day buttons 14 to 20 plus 'Any date'; 5 after the filter; the selected 20th clears to Any date with DATE_CLEARED in the polite region, and query(settled filters) has no date; both empty states). The empty-day test was watched red first, then fixed. 200 on an empty day: test_s_brw_04 test_one_showtime_must_satisfy_every_showtime_filter asserts a 200 with (0, [])

**Note:** DependsOn not yet Done: S-BRW-02, S-BRW-04. Defect fixed in logic.ts: settleListing (extracted from the ListingScreen effect) used to clear the selected day on an EMPTY response, because an empty strip contains no day. Pressing a day with nothing on it therefore showed 'Nothing is showing right now.' and refetched without the date. The effect and the seeded render share settleListing. The effect's re-request is not observed (SSR runs no effects).

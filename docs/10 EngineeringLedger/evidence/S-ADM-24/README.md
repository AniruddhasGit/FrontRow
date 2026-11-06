# S-ADM-24 — Done

Lane `p6-admin`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_24.py (7 tests) is in the '74 passed' run. This round adds the missing S-ADM-23 replay case: duplicate genre_ids sent as a PATCH return 422.

**Note:** DependsOn not yet Done: S-ADM-23, S-ADM-14, E-BRW. The booking-FK clause is asserted as showtime.movie_id -> movie_pkey plus booking.showtime_id -> showtime_pkey, through information_schema.referential_constraints JOIN key_column_usage. booking has no movie_id of its own, so the film is referenced through the showtime. The title edit is visible on the first GET /api/movies, with the real 60 s listing cache on (cached_client, Redis db 9).

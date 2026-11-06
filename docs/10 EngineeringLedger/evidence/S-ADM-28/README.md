# S-ADM-28 — Done

Clause-gap pass, 2026-11-07. The writer did not verify its own work: no second reviewer was used. That is recorded here.

**Evidence:** backend/tests/adm/test_s_adm_28.py passed 4 of 4, from `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q tests/adm/test_s_adm_28.py`.

New in test_showtimes_and_bookings_survive_and_the_first_listing_after_the_200_drops_the_film: the title is read before and after the withdrawal from three places:
- GET /api/me/bookings/{reference};
- GET /api/bookings/by-reference/{reference};
- the emailed receipt's facts, read by the worker's own query (Worker._facts, rendered by render.receipt).

All three are equal, and equal to the film's title. A before_cursor_execute listener on the api engine and on the worker engine finds a movie join, and no statement carrying published_at. For "the SES test double records zero calls", the send of every mail transport (SesTransport, StubTransport, ResendTransport) is replaced by a recorder for the unpublish request, which records zero calls. outbox_message and receipt_dispatch are also unchanged, so no later worker run sends anything.

The existing tests cover these clauses:
- version +1 and the audit before/after;
- PUBLISH_BLOCKED with its sentence;
- VERSION_CONFLICT with no change;
- the showtime and booking counts, and status, cancelled_at and total_paise unchanged;
- the first GET /api/movies after the 200 dropping the film, with the 60 s listing cache on;
- DELETE returning 405 with the movie count unchanged and no DELETE route.

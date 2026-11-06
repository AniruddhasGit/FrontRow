# S-ADM-11 — Done

Run 2026-11-07 (fork A of the blocked-rows sweep), `MSYS_NO_PATHCONV=1 docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q -p no:cacheprovider tests/adm/test_s_adm_04.py ... tests/adm/test_s_adm_18.py -rA`.

**Evidence:** backend/tests/adm/test_s_adm_11.py, 9 passed (run alone; in the combined run its module setup hit a 'tuple concurrently updated' error in roles_local.sql from parallel suites creating databases, and passed on re-run). New: test_a_hold_survives_the_start_moving_60_minutes_earlier - the seat lane's world (Redis 12), a customer holds C1 C2 on showtime 77, the admin PATCH moves starts_at 19:30 -> 18:30 local and returns 200, then EXISTS hold:{token} is 1, both lock:seat:77:* keys still exist and hold the token, and GET /api/holds/{token} returns 200 with the two seats.

# S-ADM-18 — Done

Run 2026-11-07 (fork A of the blocked-rows sweep), `MSYS_NO_PATHCONV=1 docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q -p no:cacheprovider tests/adm/test_s_adm_04.py ... tests/adm/test_s_adm_18.py -rA`.

**Evidence:** backend/tests/adm/test_s_adm_18.py, 12 passed. New: test_an_unassigned_manager_and_an_unmanaged_hall_get_200_and_empty_rows - a manager created with screen_ids [] gets GET /api/reports/showtimes?period=day 200 with rows [] and GET /api/reports/dashboard?period=day 200 with scope_empty true and films []; an admin asking GET /api/reports/showtimes for a hall no manager is assigned to gets 200 with rows []. The login refusal and every other clause were already asserted and pass.

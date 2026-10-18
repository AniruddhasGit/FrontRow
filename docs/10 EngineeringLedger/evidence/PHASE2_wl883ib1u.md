# Phase 1 close + Phase 2 build: row evidence (workflow wl883ib1u, 2026-10-18)

Each lane reported its own rows; a zero-context verifier re-checked each one. A row flips to Done only when its lane reported Done AND the verifier did not refute it. The writer never verifies its own work (Art VII).

## phase1-close (verifier verdict: PASS_WITH_DEFECTS)

### T-P1-01 — Done

**Evidence:** At HEAD 25d9649 `git grep -iE 'class (Movie|Showtime|Seat|Booking)' 25d9649 -- backend` returns nothing, and models/__init__.py is 1 line. backend/app/{api,core,domain,models,workers,jobs}/__init__.py, backend/migrations/, backend/tests/ and frontend/src/ all exist. `import app.main` passes inside the py3.12 test image: every lane test imports it, 162 passed. The frontend image build runs `npm run build` and exits 0 (frontrow-frontend:p1close built, 73.9MB).

**Note:** The 'no movie model anywhere' clause was checked at commit 25d9649. It is false in today's working tree because the Phase 2 lanes added models on purpose. scripts/ holds only README.md: there is nothing to build there yet, because seed.py and stress_seats.py belong to Phase 2 and Phase 4.

### T-P1-02 — Done

**Evidence:** tests/xct/test_s_xct_29.py::test_each_of_the_five_unset_exits_nonzero_naming_it_and_never_binds[DATABASE_URL|REDIS_URL|QUEUE_URL|JWT_SECRET|COOKIE_SECURE] passed. Real container, isolated network: `docker run ... -e JWT_SECRET= frontrow-api:p1close` exited 78 and printed {"level":"CRITICAL","logger":"app.boot","message":"configuration invalid, refusing to start: JWT_SECRET is required and is not set (or is set to an empty string)",...,"missing_or_invalid":["JWT_SECRET"]} on both stdout and stderr.

**Note:** No required variable has a default. Asserted by test_the_five_have_no_default, which passed.

### T-P1-03 — Done

**Evidence:** Real containers (p1c-api/p1c-pg/p1c-redis, isolated network): `/health/live` returned 200 {"status":"live"} with both dependencies up, and 200 {"status":"live"} with Postgres AND Redis stopped. Tests that passed: tests/xct/test_s_xct_21.py::test_live_is_200_fixed_body_and_issues_no_query_and_no_command and ::test_live_issues_no_statement_on_the_request_path_engine (a counting SQLAlchemy before_cursor_execute listener read 0).

### T-P1-04 — Done

**Evidence:** Real containers. Both up: 200 {"status":"ready","checks":{"postgres":"ok","redis":"ok"},"payment_provider":"simulated"}. Redis stopped: 503 {"status":"not_ready","checks":{"postgres":"ok","redis":"unreachable"},...}. Postgres stopped: 503 {..."postgres":"unreachable","redis":"ok"...}. Both stopped: 503 naming both. Also passed: test_s_xct_21.py::test_ready_503_names_what_is_down_while_live_stays_200[3 cases].

### T-P1-05 — Done

**Evidence:** `docker logs p1c-api` (real container, full life cycle including SIGTERM): 24 lines on stdout, 0 on stderr. Parse failures 0 of 24, and 24 of 24 lines carry request_id. `docker diff p1c-api` printed nothing, so zero files were written. Test passed: tests/xct/test_s_xct_24.py::test_every_stdout_line_of_a_real_process_is_json_with_the_seven_keys.

**Note:** The OwnedPath backend/app/core/request_id.py does not exist. The id lives in core/logging.py and core/request_context.py.

### T-P1-06 — Done

**Evidence:** `docker stop -t 30 p1c-api` gave exit code 0 on both runs. Run 1: docker stop took 2402 ms. Run 2: 6397 ms, with log `api stopped cleanly` shutdown_ms=5391; Postgres and Redis were both stopped at that point, which is the known DNS-thread delay. Both are inside the 30 s grace period. In-flight drain: tests/test_shutdown.py::test_sigterm_drains_an_in_flight_request_and_exits_zero passed (the request completed 200, a new connection was refused, exit 0). The hook list app.state.shutdown_hooks exists and is empty in Phase 1.

**Note:** The OwnedPath backend/app/core/shutdown.py does not exist. The hook list is in main.py and drain/exit is in server.py. Nothing is released in Phase 1.

### T-P1-07 — Done

**Evidence:** `docker compose up -d --build api`, then `curl -i localhost:8000/health/live` returned HTTP/1.1 200, content-type application/json; charset=utf-8, {"status":"live"}. /health/ready returned 200 with both checks ok and payment_provider simulated. The first line of docker-compose.yml reads 'LOCAL DEVELOPMENT ONLY (SRC-002 §6.1.7)'. The entrypoint's api branch only runs `exec python -m app api`, and `grep alembic|upgrade( backend/app` finds 0 hits.

**Note:** I added the 8 newly required variables to the compose api environment block and FRONTROW_REPO_ROOT plus a repo mount to the compose test service. docker-compose.yml is not in my owned list, so this is a reported cross-lane edit.

### T-P1-08 — Blocked

**Evidence:** `docker images`: frontrow-api:p1close is 286MB, which is OVER the 250 MB budget. `docker image inspect -f '{{.Size}}'` gives 66623552 bytes (compressed content store). Size by layer: the venv is 84.6MB, including sqlalchemy at 28MB. frontrow-frontend:p1close is 73.9MB.

**Note:** The Phase 2 dependencies the foundation lane added (sqlalchemy[asyncio], alembic, pyjwt, bcrypt) took the API image from 239MB to 286MB by docker images, so it does not fit the 250 MB budget on that measure. It does fit on the inspect/compressed measure that S-XCT-35 uses. Which measure the budget means is an open client question. The second clause needs a reviewer who is not the author to confirm the Zone B comments; this lane edited them, so it cannot confirm them itself.

### T-P1-09 — Blocked

**Evidence:** tests/xct/test_s_xct_40.py::test_every_named_spec_exists_and_carries_the_four_headings and ::test_every_queue_row_is_needed_by_a_phase passed. All 10 P1_*.md specs now carry exactly '## What to build', '## What the application expects', '## Acceptance criteria' and '## Common mistakes' (3 items each). Every queue row has a Needed by value matching ^Phase [1-8]. test_no_zone_c_artefact_by_path passed.

**Note:** The 'said in chat' clause cannot be checked from the repository. The new Phase 1 AWS needs listed in aws_needs must be announced in chat by the orchestrator before this row can close.

### S-SCP-01 — Done

**Evidence:** tests/scp/test_s_scp_01.py: 8 passed. They cover contract endpoint_count == 58, mounted-minus-contract empty against the working tree's routers (FastAPI 0.143 _IncludedRouter walked through effective_candidates), no excluded-path match, and the 5 excluded URLs each returning 404, content-type application/json; charset=utf-8, error.code NOT_FOUND and an 8-hex request_id. Live compose check: GET /api/export/bookings.csv returned 404, application/json; charset=utf-8, {"error":{"code":"NOT_FOUND","message":"That page does not exist.","details":{},"request_id":"f2d8c07c"}}.

**Note:** charset=utf-8 is added once, centrally, in core/request_context.py for every application/json response.

### S-SCP-02 — Backlog

**Evidence:** tests/scp/test_s_scp_02.py: 3 passed. They cover no scheduler library or call outside comments, no excluded manifest dependency, and no model or movie-API host.

**Note:** The compose clause says 'exactly three services', which contradicts S-XCT-35 and S-XCT-36 (six services). I filed it as a doc defect and wrote no test for it. The outbound-request sublist test for one end-to-end checkout needs Phase 4 and Phase 5.

### S-SCP-03 — Done

**Evidence:** tests/scp/test_s_scp_03.py: 4 passed. Covered: no field matching TMDB|MOVIE_API|API_KEY|SCHEDULE|CRON|SWEEP; PAYMENT_PROVIDER unset exits non-zero with PAYMENT_PROVIDER on stderr and the port refused; PAYMENT_PROVIDER=stripe exits non-zero with 'simulated' on stderr; /health/ready 200 with payment_provider simulated.

### S-XCT-21 — Done

**Evidence:** tests/xct/test_s_xct_21.py: 15 passed. Covered: live issues 0 probes and 0 SQLAlchemy statements (counting before_cursor_execute listener on the real engine); ready 200 body with checks and payment_provider; 503 for postgres, redis and both while live stays 200; ready stays 200 with SQS, SES and S3 pointed at unroutable endpoints; a real server process against a blackholed (accept-and-never-answer) Postgres returns 503 in under 2 s with a 10 s httpx client timeout; a second request inside the 3 s TTL issues no probe; no cookie needed; no version, hostname or URL in the body; 'restart loop' appears in health.py; /health/ready appears on the load balancer queue row; the 'reversing them...' sentence is in P1_ALB.md. Real stopped-container outputs are listed under T-P1-03 and T-P1-04.

**Note:** The 'counting Redis client wrapper' is the counting readiness probe, because that probe is the only Redis caller in the process.

### S-XCT-22 — Backlog

**Evidence:** Not tested by this lane. Existing tests cover 404, 405 and 500 envelopes and the trace staying in the log (tests/test_logging.py::test_unhandled_exception_is_500_envelope_and_trace_stays_in_the_log, ::test_unknown_path_is_404_envelope, ::test_wrong_method_is_405_envelope, all passed).

**Note:** Its OwnedPath backend/app/api/errors.py now belongs to another lane, which moved core/errors.py there. Several clauses need later work: the 500 message with 'quote {request_id}', a sweep forcing failures on every mounted route, the frontend branching tests, SEAT_UNAVAILABLE and the five 409 interface branches (Phase 3 to 4).

### S-XCT-24 — Backlog

**Evidence:** tests/xct/test_s_xct_24.py: 6 passed. Covered: every stdout line of a real process is JSON with the seven keys; no FileHandler or open(.log); the generated id in X-Request-Id on 200, 404 and 500; an injected id recorded as client_request_id; one INFO 'request completed'; two live polls write no INFO line and a ready failure writes a WARNING; no JOIN on request_id. Also tests/test_logging.py: 19 passed.

**Note:** Two clauses are left for later: SEAT_UNAVAILABLE at INFO with seat_conflicts_total (Phase 4), and the pg_indexes unique-index check on request_id, which needs the schema applied (foundation lane).

### S-XCT-26 — Backlog

**Evidence:** tests/xct/test_s_xct_26.py: 4 passed. Covered: the five keys are redacted with no call-site change; a real process's stdout has no bcrypt hash, JWT, 'Authorization: Bearer' or 13-19 digit run, even when Bearer and JWT-shaped cookie headers are sent; the LOG_LEVEL default is INFO and logging.py contains no ENVIRONMENT or APP_ENV; LOG_LEVEL=DEBUG is refused in P1_CLOUDWATCH_LOGS.md.

**Note:** Not done yet: the seeded-password scan (seed is Phase 2) and the scan for a reference beside an @ over the receipt and booking log paths (Phases 4 and 5).

### S-XCT-28 — Done

**Evidence:** tests/xct/test_s_xct_28.py: 6 passed. Covered: exactly one queue row naming 'CloudWatch alarm', Needed by Phase 1, with the running-task-count < 1, SNS topic and email subscription literals; no alarm definition in the executable trees; P1_TASK_COUNT_ALARM.md carries 'TreatMissingData: breaching', INSUFFICIENT_DATA, the acceptance sentence, the 'Recommended, not adopted' sentence, and the '## Not watched, and deliberately so' list starting with '- dead-letter queue depth' with a later S3 poster bucket item; no committed destination address; no create-topic, put-metric-alarm or subscribe command.

### S-XCT-29 — Backlog

**Evidence:** tests/xct/test_s_xct_29.py: 26 passed. Covered: each of the five unset exits non-zero naming it on stdout and stderr with the port never bound; the five have no Field() default; API_PORT=80 names the variable and the bound 1024; CROSS_FIELD_CHECKS is a tuple of 13 uniquely named entries; checks 1, 2, 3, 5 and 12 each asserted (check 12 with equal ports, 80 and 70000, in the api process); 'configuration resolved' logged exactly once by a real process with SECRET|PASSWORD|TOKEN|URL redacted and PAYMENT_PROVIDER present; no ENVIRONMENT, APP_ENV or is_prod in backend/app; Settings plus SeedSettings names equal the .env.example names; a comment line directly above every .env.example assignment; the .env.example SEED_DEFAULT_PASSWORD refused by the seed placeholder check; no AKIA or private key in .env.example; a comment above every config.py assignment.

**Note:** Every clause Phase 1 can reach passes. Two remain: the WORKER half of 'exit non-zero in both the api and the worker process' (the worker arrives in Phase 5), and S-XCT-48's full seed checks. I implemented only the placeholder refusal; the length bounds are Phase 2.

### S-XCT-30 — Done

**Evidence:** tests/xct/test_s_xct_30.py: 7 passed. Covered: no ssm, get_parameter or parameter_store in backend/app (zero boto3 clients so far); the SSM spec named by the 'SSM Parameter Store' row (Needed by Phase 1) carries all 7 literals; the '## SecureString parameters' (3 rows) and '## Plain environment variables' (62 rows) tables are disjoint, SEAT_HOLD_TTL_SECONDS is plain only, and together they equal Settings.model_fields; 'secrets manager' appears only on lines saying forbidden; .env is in .gitignore; the credential regex over the whole repo and docs/05 Bible finds 0 hits; no put-parameter, iam create or register-task-definition. Host check: `git check-ignore .env` printed .env and exited 0.

**Note:** To meet the 0-hit ssm scan I reworded one comment in another lane's backend/app/db/__init__.py ('RDS and SSM' became 'RDS and Parameter Store'). The 'boto3 returns only s3, sqs, ses' clause holds only because no boto3 client exists yet.

### S-XCT-31 — Backlog

**Evidence:** tests/xct/test_s_xct_31.py: 1 passed. Both literals are in P1_TASK_DEFINITIONS.md: 'the ECS stop timeout must exceed the deregistration delay plus SHUTDOWN_DRAIN_TIMEOUT_SECONDS' and 'SIGKILL arriving during the drain skips the release'. The drain itself is covered by tests/test_shutdown.py::test_sigterm_drains_an_in_flight_request_and_exits_zero, which passed.

**Note:** Still to come: the Redis hold registry instance:{id}:holds, compare-and-delete release, TTL and SIGKILL survival (Phase 4), and the worker's SIGTERM drain (Phase 5).

### S-XCT-32 — Backlog

**Evidence:** tests/xct/test_s_xct_32.py: 2 passed. Covered: API_PORT=80 exits non-zero naming API_PORT, and API_PORT appears in docs/30. Real container: read-only root filesystem with `docker diff p1c-api` empty, `docker exec p1c-api id` showing uid=10001(frontrow), and `-e API_PORT=80` giving exit code 78.

**Note:** Still to come: poster upload (Phase 6), the fr.pending_selection round trip (Phase 3), rate-limit buckets and hold registry surviving SIGKILL (Phases 4 and 7), SIGKILL mid-confirm (Phase 4), and the worker image (Phase 5).

### S-XCT-35 — Backlog

**Evidence:** Measured locally at idle: frontrow-api-1 70.39MiB / 200MiB, frontrow-frontend-1 2.922MiB / 15MiB (docker stats). The api image is 286MB by docker images and 66623552 bytes by docker image inspect. No test written.

**Note:** Compose has no worker, web or elasticmq service yet (the frontend service is named 'frontend'), the worker does not exist (Phase 5), and the under-load measurement is Phase 7. This lane did not write the spec literals or the per-container memory lines.

### S-XCT-36 — Backlog

**Evidence:** tests/xct/test_s_xct_36.py: 2 passed. Scheduler words appear only on lines saying 'no scheduled job', and there is no DELETE FROM or EXPIRE on idempotency.

**Note:** Still to come: the six-service compose list (worker and elasticmq arrive in Phase 5), hold expiry against real Redis (Phase 4), the outbox relay and SCAN (Phase 5), the seat-map cache TTL (Phase 3), and the DELETE FROM allow-list (later phases).

### S-XCT-37 — Done

**Evidence:** tests/xct/test_s_xct_37.py: 6 passed. Covered: no task-queue or argon2 requirement; no forbidden JS library; every package in both manifests is on the recorded allowlist in the test; forbidden services appear only on lines saying forbidden (backend/app, migrations, frontend/src, docs/30); no minio or mailhog in compose; the 'local development does not fully exercise...' sentence is in P1_EC2_ECS_CLUSTER.md; '## Services this product uses' lists exactly the 10 services.

**Note:** The allowlist includes sqlalchemy, alembic, pyjwt, bcrypt (added by the Phase 2 lane) and boto3, with the source for each. A new package fails this test until someone records it there.

### S-XCT-40 — Done

**Evidence:** tests/xct/test_s_xct_40.py: 8 passed. Covered: no *.tf, workflow, taskdef or cloudformation path; no 'reference only'; every non-em-dash Spec cell links an existing docs/30 file with the four headings and 2-3 mistakes; no Terraform, CloudFormation or containerDefinitions block; every Needed by matches ^Phase [1-8]; only describe, list or get aws verbs; the '(reasoned, not observed)' marker is on every 'in AWS' paragraph; every Zone B logical line (both Dockerfiles, entrypoint.sh, config.py, health.py) is preceded by a comment line.

**Note:** [JUDGMENT CALL] I read the comment rule per LOGICAL line: a Dockerfile or shell `\` continuation and a bracketed Python expression each count as one unit. Queue rows 19, 20, 25, 26 and 31 had prose in their Spec cell; that prose moved into the Item cell and the Spec cell is now an em dash. Row 20's Needed by changed from '**Phase 1**' to 'Phase 1'.

### S-XCT-41 — Backlog

**Evidence:** tests/xct/test_s_xct_41.py: 4 passed. Covered: every Bible story has Milestone 1-8 and no DependsOn edge runs backwards; S-XCT-01 (M4) reaches S-XCT-48 (M2) and then S-XCT-44 (M2); no skip or xfail marker and no bare-pass test; docs/30 Deployment/PHASE_1_CLOSE.md carries the 3 headings plus '## What to test' with numbered steps.

**Note:** 'Parsing the eight files' cannot hold until Phases 2 to 8 each write their close-out file.

### S-XCT-42 — Backlog

**Evidence:** tests/xct/test_s_xct_42.py: 3 passed. Covered: COOKIE_SECURE is required and declared with no default; the TLS phrases have 0 hits in docs/03 PRD, docs/30, backend/app, migrations and frontend/src; no cancel, withdraw or refund in mounted paths; refund|cancel_showtime has 0 hits; cancelled_at has 0 hits in backend/app/api; no 'receipt failed' copy in frontend/src; OPEN-EMAILFAIL-01 is in the PRD.

**Note:** The AC's rg pattern also includes 'withdraw', and that word now matches the Phase 2 audit vocabulary in backend/app/domain/audit.py ('language.withdrawn' and others). I filed the conflict and did not assert that word. Still to come: seed.py, the movie table, the cancelled_at column check and the booking-screen reference (Phases 2 and 4).

### S-XCT-47 — Backlog

**Evidence:** tests/xct/test_s_xct_47.py: 2 passed. Model vocabulary appears only on lines saying 'no artificial-intelligence feature', and there is no boto3 client other than s3, sqs or ses.

**Note:** Still to come: 'exactly three boto3 clients' (Phases 5 and 6), the socket-level allowlist over the whole suite (left out on purpose: a hostname allowlist at connect() sees IPs and would break the DB lanes' tests), and the listings ORDER BY (Phase 3).

### E-SCP — Backlog

**Evidence:** Children: S-SCP-01 Done, S-SCP-03 Done, S-SCP-02 Backlog.

**Note:** An epic closes when all its children are Done.

### E-XCT — Backlog

**Evidence:** M1 children Done: S-XCT-21, S-XCT-28, S-XCT-30, S-XCT-37, S-XCT-40. The rest are Backlog.

**Note:** An epic closes when all its children are Done.

## p2-foundation (verifier verdict: PASS_WITH_DEFECTS)

### S-XCT-04 — Done

**Evidence:** backend/tests/xct/test_s_xct_04.py: test_upgrade_head_on_empty_database_creates_exactly_one_unique_constraint_on_booking_seat, test_table_and_its_unique_constraint_are_written_in_the_same_single_revision_file, test_no_revision_drops_a_constraint, test_the_guard_is_total_no_where_clause_and_not_a_partial_index all PASS (lane run: 111 passed / 5 failed, none of the 5 is one of these). Also passing: test_the_constraint_refuses_a_second_seller, test_migrated_catalog_is_identical_to_the_catalog_schema_sql_produces (columns, constraints, indexes, grants, owners, sequence grants equal the schema.sql-built database), test_the_orm_mirror_matches_the_migrated_columns. Red-proof: with sa.UniqueConstraint('showtime_id','seat_id') removed from the revision, 4 of these tests went red ('4 failed, 4 deselected'), then the line was restored.

**Note:** The AC is fully proved. The same file also holds test_verify_invariants_sql_passes_as_the_application_role. It is RED, and it is not part of this AC. 36 checks pass. A4 fails only on '(table count mismatch)', because Alembic's alembic_version table sits in public. Defect is in docs/06 checks/verify_invariants.sql (see doc_defects). The test is left red on purpose.

### S-XCT-05 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_05.py: 27 PASS. They cover: ratio 100 loads; ratios 1000/10/1 with INR raise ConfigError naming CURRENCY_MINOR_UNIT_RATIO; the currency is present in the one resolved-config line; pricing.py has exactly one public function, seat_price_paise(base_price_paise: int, uplift_basis_points: int) -> int; 25000@3333 gives 33333 and three seats total 99999, not 99998; 30938, 36666, 27500 and 166146 match P-PAY-03/04; floats, Decimal, strings and bools are TypeError; negatives are ValueError; uplift_basis_points has 0 hits outside pricing/models/migrations; PositivePaise refuses 250.00, -1 and 0 with 422 VALIDATION_FAILED details {field: base_price_paise}; SUM is Decimal raw and int after cast(BigInteger). RED: test_every_price_amount_total_column_is_bigint_and_named_paise returns ('booking_seat','base_price_paise_applied','bigint'). Mutation: with half-up changed to floor, 4 tests went red, then the change was restored.

**Note:** Blocked for four reasons. (1) The AC's census query cannot return 0 rows against the schema of record: base_price_paise_applied contains 'price' but does not end in _paise. That is a doc defect. (2) The AC's rg 'float\(|:\s*float|->\s*float' over backend/app hits Phase 1 non-money code (READINESS_CACHE_TTL_SECONDS: float, Clock.monotonic -> float), so it is not asserted. (3) The 'exactly five importing files' clause waits on the seat-map, checkout, receipt, dashboard and seed lanes. (4) POST/PATCH /api/admin/showtimes belong to the admin lane; the strict PositivePaise type it must use exists.

### S-XCT-06 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_06.py: 10 PASS. The change and the audit row commit together with every field (actor 17, admin, showtime.base_price_changed, showtime, 41, before/after, a generated 8-hex request_id). With write_audit patched to raise, the price stays 25000 and the count is unchanged. A failing UPDATE leaves 0 audit rows. actor_user_id is NOT NULL with one FK to users(id). actor_role still reads admin after the user's role changes to manager. jsonb_object_keys counts 1/1, and before IS NULL on a creation. occurred_at is 'timestamp with time zone', and the bound parameter captured by a before_cursor_execute listener is aware with utcoffset 0. Naive and +05:30 instants are refused.

**Note:** Every clause is proved at the mechanism level (app/core/audit.py in the caller's transaction, as frontrow_app). The AC's request path is EP-ADM-11 (PATCH /api/admin/showtimes/{id}), with the request_id read from the response, and that endpoint belongs to the admin lane. Re-run these assertions through that endpoint when it lands.

### S-XCT-07 — Done

**Evidence:** backend/tests/xct/test_s_xct_07.py: 8 PASS. information_schema.table_privileges for current_user frontrow_app is exactly [INSERT, SELECT]. UPDATE and DELETE on audit_log as frontrow_app raise InsufficientPrivilege. Both through HTTP give 500 INTERNAL_ERROR with message 'The server could not complete this request. If you need help, quote {request_id}.', where request_id matches ^[0-9a-f]{8}$ and equals X-Request-Id. 'base_price_changed' is refused with 500 and showtime 41 is never 28000 (count 0); 'showtime.base_price_changed' is accepted. AUDIT_ACTIONS is the module-level tuple in backend/app/domain/audit.py (39 members, transcribed from P-ADM-19). Every action= literal in backend/app is a member. Mutation: with the boundary check removed, the paraphrase test went red, then it was restored.

**Note:** The two HTTP clauses use a route mounted by the test on the real app. No product endpoint may ever UPDATE audit_log, and EP-ADM-11 does not exist yet. That route uses the documented handler pattern: check_action() before conn.begin(), then write_audit() inside it. The admin lane's real handler must call check_action() before begin(); re-verify there.

### S-XCT-09 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_09.py PASS: zero foreign keys have confdeltype <> 'r' (more than 20 exist); booking.user_id is NOT NULL with FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE RESTRICT ON DELETE RESTRICT; DELETE FROM users WHERE id = 4471 with a booking raises ForeignKeyViolation, sqlstate 23503, as the owner (the app role lacks DELETE entirely); the DELETE FROM (booking|...) scan of backend/app and backend/migrations finds 0 hits. RED: test_every_table_except_alembic_version_and_audit_log_carries_created_at returns movie_genre, receipt_dispatch, showtime, showtime_seat.

**Note:** Blocked on two things. (1) A data-model defect: four tables in schema.sql/datamodel.json have no created_at, so the AC's census cannot pass. The fix belongs in docs/06 datamodel.json plus a new migration, never an edit to 0001. (2) The 'exactly three DELETE routes' walk needs EP-ADM-21 and EP-HLD-03/04 from other lanes.

### S-XCT-10 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_10.py: 11 PASS. The admin, manager and auth_session routers each carry exactly their one dependency (require_admin, require_reporting, current_user); auth and browse carry none. app.routes holds no APIRouter, and every /api/admin and /api/reports route carries its dependency. No role-check pattern appears in backend/app/api outside deps.py. No session gives 401 'Sign in to continue.'. An expired session (FakeClock advanced 43200 s) and a bad signature give 401 'You were signed out. Sign in again to continue.'. The wrong role gives 403 FORBIDDEN. A role changed in the DB applies on the very next request with the same cookie, and a password_version bump gives 401. A manager's PATCH /api/admin/showtimes/101 with an invalid body gives 403, while an admin with the same body gets 422. The reporting router mounts no write method. Mutation: with the admin router's dependency removed, the test went red, then it was restored.

**Note:** Blocked for three reasons. (1) The customer router (/api/me, /api/bookings, /api/holds) is one of the AC's four routers, but no module exists yet; the brief listed only auth, auth_session, admin, manager and browse. (2) The 401/403 and 403-before-422 behaviour is proved on a router the test builds with the same dependency objects, because the real PATCH /api/admin/showtimes route belongs to the admin lane. (3) The AC's rg path backend/app/api/routes does not exist (doc defect); the equivalent scan runs over backend/app/api.

### S-XCT-12 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_12.py: 10 PASS. 11 characters gives 'Use a password of at least 12 characters.'. 12 Devanagari characters (36 bytes) pass, because the floor counts characters. 25 Devanagari characters (75 bytes) give the 72-bytes message. 72 Latin characters are accepted and round-trip. The hash is $2b$ and never the plaintext. An unknown email runs exactly one bcrypt.checkpw, against a dummy hash. bcrypt hashpw/checkpw/gensalt appear only in core/security.py, which has no 'async def'. users has exactly one CREATE UNIQUE INDEX on lower(email). Nikhil@Example.invalid is stored as entered, and nikhil@example.INVALID then hits UniqueViolation. No password or password_plain column exists.

**Note:** Blocked on the account lane: registration 422/409 EMAIL_ALREADY_REGISTERED, sign-in 401 CREDENTIALS_INVALID, email 254/255, to_thread.run_sync in the auth router, and no plaintext in stdout or response. The primitives they call exist: password_problem, hash_password, verify_password(password, None, cost) for the dummy-hash path.

### S-XCT-13 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_13.py: 9 PASS. set_session_cookie parsed from Set-Cookie carries fr_session, HttpOnly, SameSite=lax, Path=/, Max-Age=43200, and Secure only when COOKIE_SECURE=true (both settings). Clearing repeats the attributes with Max-Age=0. COOKIE_SECURE absent gives ConfigError naming it. COOKIE_SECURE=true with an http:// PUBLIC_BASE_URL is refused naming both. frontend/src is mounted and holds 0 localStorage hits, and backend/app plus frontend/src hold 0 samesite=none hits. Host rg gives the same: rc=1 for both scans.

**Note:** Blocked for three reasons. A real sign-in response (EP-ACC-02, account lane) must call set_session_cookie. The 'every GET mutates nothing' walk with pg_stat_xact_user_tables is not written yet, because no product GET route exists. The sessionStorage fr.selection clause belongs to the seat lane's frontend. The boot exit naming COOKIE_SECURE is enforced by the config lane's config.py (S-XCT-29).

### S-XCT-23 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_23.py: 7 PASS. POST, PUT, PATCH and DELETE on /health/live each give 405 with the envelope METHOD_NOT_ALLOWED, 'That action is not available. Nothing was changed.', empty details, a fresh 8-hex request_id, and an Allow header containing GET. GET /api/nothing-here gives 404 NOT_FOUND. 'method_not_allowed' appears on exactly one line, in app/api/errors.py (host rg -c gives 1). The 405 body is identical across paths and methods. The live compose API answers POST /health/live with 405 in the envelope.

**Note:** Blocked: DependsOn S-XCT-22, which is not this lane. The DELETE clauses on /api/admin/{movies,showtimes,screens,cinemas,lookups} and the four verbs on /api/reports/dashboard need those GET/PATCH routes to exist; until then the paths are 404. DELETE /api/admin/seats/{seat_id} gives 204 under EP-ADM-21, which is the admin lane's. The contract.json METHOD_NOT_ALLOWED clause was not re-checked by me.

### S-XCT-33 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_33.py: 9 PASS. 'alembic' and 'upgrade(' have 0 hits in backend/app (host rg rc=1). Alembic appears in entrypoint.sh only inside the migrate) branch, as 'exec alembic -c migrations/alembic.ini upgrade head'. migrate exits 0, and 0 again on a re-run. Run as frontrow_app it exits non-zero with 'permission denied' and leaves 0 tables, so the transaction is all-or-nothing. The API against an unmigrated database gives /health/live 200 and /health/ready 200 with real postgres and redis probes, then 500 INTERNAL_ERROR at the first query touching movie. The downgrade in 0001 is a single Raise(NotImplementedError). Revisions touching audit_log or booking_seat carry '# LOCK:'. There is no drop_column, drop_table or alter_column. frontrow_app has rolsuper=false; checked live too, with the compose DATABASE_URL via psql: 'frontrow_app|f'. 'docker compose --profile tools run --rm migrate' applied revision 0001 to the local frontrow DB.

**Note:** Blocked for three reasons. DependsOn S-XCT-29 (another lane). The entrypoint must accept exactly api, worker, migrate and seed; worker (Phase 5) and seed (seed lane) do not exist, so I did not invent them. The docs/30 Deployment runbook strings are not mine to write. With only one revision, 'one revision behind' was tested as an unmigrated database.

### S-PAY-01 — Blocked

**Evidence:** backend/tests/pay/test_s_pay_01.py: 10 PASS. INR with ratio 100 boots. 0, 1.5 and abc are refused naming the ratio. A subprocess with ratio 0 or 1.5 exits non-zero, stderr names CURRENCY_MINOR_UNIT_RATIO, and a connection to its API_PORT is refused. pricing.py has no float( or Decimal. backend/app/api and backend/app/domain contain no rupee sign. The ratio is assigned once, in app/core/config.py. pricing.py has no literal-100 multiply or divide. RED: test_an_unset_ratio_is_refused_naming_it (config.py defaults the ratio to 100) and test_the_money_columns_are_exactly_four_and_all_bigint (the AC's LIKE '%_paise' returns 3 rows: total_paise, price_paise, amount_paise).

**Note:** Blocked for three reasons. POST /api/bookings (EP-PAY-01) and its 201 body clauses are Phase 4. The AC conflicts with PRD S7.9 on the default: S7.9 publishes 100 and the config lane implemented that, while the AC says unset must exit. The AC's own query cannot return base_price_paise_applied. api/bookings.py and domain/payment do not exist, so those rg clauses are not yet meaningful.

### S-ACC-07 — Backlog

**Evidence:** Not built. Only its table (password_reset_token) exists, created by migration 0001.

**Note:** Phase 5 per JC-R6-02

### S-ACC-08 — Backlog

**Evidence:** Not built. Only its table (password_reset_token) exists, created by migration 0001.

**Note:** Phase 5 per JC-R6-02

## p2-accounts (verifier verdict: PASS_WITH_DEFECTS)

### S-ACC-01 — Done

**Evidence:** backend/tests/acc/test_s_acc_01.py, 6 PASS: test_register_returns_201_sets_the_session_and_stores_one_customer_row (201, fr_session set, body exactly {user_id,email:'Ada@Example.com',role:'customer'}, one row with role customer / password_version 1 / last_signed_in_at NULL, hash != password, 'correct horse battery' absent from the body, from the DEBUG log stream plus captured stdout for the whole request, and from users::text), test_the_users_table_has_exactly_the_seven_columns, test_a_second_registration_in_another_case_is_409 (409 EMAIL_ALREADY_REGISTERED with the exact sentence), test_twenty_simultaneous_identical_registrations_make_one_account (RATE_LIMIT_REGISTER_IP_PER_HOUR=25: [201]+[409]*19, no RATE_LIMITED, no 5xx, count 1), test_the_bucket_is_still_counting_during_the_larger_bucket_run (the 26th request is 429, so the limiter was live during that run), test_role_is_never_read_from_the_request_body. Lane run: 66 passed, 4 failed in 41.50s. None of the 4 is in this file.

**Note:** Reused the existing 0001 migration, which already holds the users table and uq_users__email_ci. A simultaneous twin's unique violation is caught by constraint name and becomes 409.

### S-ACC-02 — Blocked

**Evidence:** backend/tests/acc/test_s_acc_02.py, 9 PASS: test_eleven_characters_is_refused_with_the_interpolated_floor, test_the_floor_is_read_from_configuration_not_a_literal (PASSWORD_MIN_LENGTH=14 gives 'at least 14 characters'), test_84_bytes_is_refused_quoting_the_submitted_byte_count (28 code points, 84 bytes, details.byte_length=84), test_spaces_are_kept_and_no_composition_rule_applies, test_bcrypt_hashing_runs_off_the_event_loop_thread (test on the main-thread loop through httpx ASGITransport; the recorded flags are [False]), test_sign_in_verifies_exactly_once_on_every_branch (unknown, wrong password and sentinel-hash account each give +1 verify and 401 CREDENTIALS_INVALID), test_password_hash_is_not_null_and_no_two_unused_accounts_share_a_hash, test_no_assertion_in_this_module_reads_a_clock_or_sleeps. Mutation: calling bcrypt inline instead of to_thread turned the off-loop test red; the change was then restored.

**Note:** Register and login clauses are all proved. The AC also covers 'register OR reset-confirm', and EP-ACC-06 ships in Phase 5 (SRC-004 JC-R6-02). The reset-confirm half of the 11-character clause cannot run yet. Flip to Done when Phase 5 re-runs it, or split the row.

### S-ACC-03 — Done

**Evidence:** backend/tests/acc/test_s_acc_03.py, 10 PASS: test_sign_in_in_any_case_returns_200_and_writes_only_last_signed_in_at (200, cookie, body; last_signed_in_at equals the injected instant; email/password_hash/role/password_version/created_at identical before and after; 0 audit rows), test_unknown_address_and_wrong_password_are_identical_but_for_the_request_id (same status, Content-Type, key set and body once request_id is removed; request_ids differ; exact message; last_signed_in_at stays NULL), test_a_missing_or_empty_field_is_422 x6 ('Enter your email address and password.'), test_a_ten_character_stored_password_still_signs_in, test_nine_failures_lock_nothing_and_the_tenth_attempt_signs_in (9 x 401, role unchanged, exactly the seven columns, 10th attempt 200).

### S-ACC-04 — Done

**Evidence:** backend/tests/acc/test_s_acc_04.py, 15 PASS: test_the_cookie_attributes_with_secure_from_configuration[false/true] (exactly HttpOnly, SameSite lax, Path=/, Max-Age=43200, Secure iff COOKIE_SECURE=true), test_the_process_refuses_to_start_without_the_variable_and_names_it_on_stderr[COOKIE_SECURE/JWT_SECRET] (subprocess `python -m app api`, non-zero exit, name present in stderr), test_the_token_carries_exactly_five_claims_and_no_email, test_a_password_version_behind_the_row_is_refused, test_a_removed_user_row_is_refused ('Sign in to continue.'), test_a_token_missing_one_claim_is_refused_not_defaulted[sub/role/pv/iat/exp] (five separate 401 AUTH_REQUIRED), test_a_role_changed_in_the_database_applies_on_the_next_request, test_sign_out_is_204_with_a_matching_clearing_cookie_in_every_state (signed in, no cookie, expired, malformed, second call: each 204 with 'fr_session=;' + Max-Age=0 and the issued attributes), test_no_session_table_exists.

**Note:** Required foundation edits in security.py: all five claims are now required, and the clearing cookie is written as 'fr_session=;'. Starlette renders an empty value as "". SameSite is emitted as 'lax' and asserted case-insensitively.

### S-ACC-05 — Done

**Evidence:** backend/tests/acc/test_s_acc_05.py, 7 PASS: test_the_lifetime_is_twelve_hours_on_the_injected_clock (clock at 2026-08-14T10:00:00Z gives iat 10:00:00Z, exp 22:00:00Z and Max-Age=43200; 21:59:00Z is 200; 22:00:01Z is 401 'Your session has ended. Sign in to continue.'; the injected clock is two months off the container clock), test_a_zero_or_non_integer_lifetime_fails_startup_naming_the_variable[0/twelve/1.5] (stderr names SESSION_TTL_SECONDS), test_no_refresh_route_exists_in_the_contract_or_the_running_app (no refresh/renew/reissue/exchange/session path in contract.json or the mounted routes; contract token paths are exactly EP-HLD-02/03/04; app token paths are a subset of those), test_43200_appears_once_in_the_codebase_and_only_in_config, test_no_test_in_this_module_reads_a_clock_or_sleeps.

**Note:** Expiry is the app's own exp comparison against the injected clock. verify_exp is off in decode_session_token.

### S-ACC-06 — Blocked

**Evidence:** backend/tests/acc/test_s_acc_06.py: 3 PASS (test_a_new_account_reaches_me_at_once_with_exactly_three_keys, test_registration_enqueues_nothing, test_a_second_account_does_not_move_the_first_booking). 3 RED: (a) test_no_response_body_speaks_of_verification: the 5th body, POST /api/auth/password-reset/request, gives 404 not 202; (b) test_exactly_four_operations_take_an_email_and_none_is_a_patch_or_put: the OpenAPI set lacks ('POST','/api/auth/password-reset/request'), while register, login and the admin lane's POST /api/admin/managers are present and no PATCH/PUT takes an email; (c) test_users_email_is_never_in_an_update: it drives register, login, logout, POST /api/admin/managers and PUT /api/admin/managers/{id}/screens, and records {'last_signed_in_at'}. 'email' is never in it, but password_hash and password_version only appear once reset-confirm exists.

**Note:** All three red clauses wait only on EP-ACC-05/06, Phase 5 per SRC-004 JC-R6-02. The tests are written as the AC states and left red on purpose, not skipped. The 'users mapper before_update listener' is a Core before_execute listener, because no mapper exists (see judgment_calls).

### S-ACC-07 — Backlog

**Evidence:** No code and no test. The password_reset_token table already exists in migration 0001.

**Note:** Phase 5 per JC-R6-02

### S-ACC-08 — Backlog

**Evidence:** No code and no test.

**Note:** Phase 5 per JC-R6-02

### S-ACC-09 — Blocked

**Evidence:** backend/tests/acc/test_s_acc_09.py, 11 PASS: test_the_11th_sign_in_for_one_email_is_refused_with_retry_after_90 (429 RATE_LIMITED, Retry-After 90, exact sentence), test_the_31st_sign_in_from_one_ip_is_refused_by_the_ip_bucket (31 distinct emails, Retry-After 30), test_the_6th_registration_from_one_ip_in_an_hour_waits_12_minutes (Retry-After 720, '12 minutes'), test_retry_after_is_the_time_to_the_next_token_not_a_constant (90 at t=0, 60 at t=30), test_refill_follows_the_injected_clock_and_the_key_ttl_is_only_a_backstop (admitted 90 s later while PTTL > 0), test_the_lua_script_never_asks_redis_for_the_time, test_forged_leftmost_forwarded_for_values_share_the_real_clients_bucket, test_the_same_holds_when_uvicorn_rewrites_the_peer_from_the_header, test_an_untrusted_peer_cannot_choose_its_bucket_with_the_header, test_either_empty_bucket_alone_refuses, test_spans_render_by_s7_20. RED: test_with_redis_unreachable_sign_in_fails_closed_and_browsing_still_works. Login and register 503 DEPENDENCY_UNAVAILABLE with their exact sentences pass, but GET /api/movies is 404. Mutation: forcing elapsed=0 in the Lua turned the Retry-After-60 and refill tests red; the change was then restored.

**Note:** Blocked on two things. (1) EP-BRW-01 GET /api/movies does not exist yet; it belongs to the browse lane, Phase 3. (2) The reset-request and reset-confirm buckets (6th request, 11th confirm, separate confirm bucket, a token spent on a malformed confirm) need EP-ACC-05/06, Phase 5 per JC-R6-02. They are not tested here.

### S-ACC-10 — Done

**Evidence:** backend/tests/acc/test_s_acc_10.py, 5 PASS: test_booking_user_id_is_not_null_and_its_foreign_key_restricts (confdeltype 'r', is_nullable NO), test_the_migration_declares_the_restrict (0001 holds the fk_booking__user_id ... ON DELETE RESTRICT line), test_deleting_a_user_with_a_booking_is_refused_then_red_proved_then_restored (23503 with counts unchanged; then CASCADE: the delete succeeds and booking, user and booking_seat counts are 0/0/0; then RESTRICT is restored, confdeltype is 'r' again and a fresh delete gives 23503), test_a_user_with_no_booking_can_be_deleted_and_its_session_then_ends (401 'Sign in to continue.'), test_no_route_takes_a_booking_owner_from_the_request (58 contract endpoints; only EP-ADM-24 carries {user_id}; no owner field under /api/bookings, /api/me/ or /api/showtimes; the DELETEs are exactly ADM-21, HLD-03 and HLD-04; the mounted routes agree).

**Note:** The red-proof also flips fk_booking_seat__booking_id to CASCADE and back (see doc_defects).

## p2-admin (verifier verdict: PASS_WITH_DEFECTS)

### S-ADM-03 — Done

**Evidence:** backend/tests/adm/test_s_adm_03.py, 7 passed ('tests/adm/test_s_adm_03.py .......'). The tests: test_list_is_ordered_and_carries_every_field, test_rename_with_matching_version_is_200_version_plus_one_and_one_cinema_updated_row, test_name_and_zone_in_one_request_write_two_rows, test_an_unknown_zone_a_121_character_name_and_a_taken_name_are_422_with_nothing_written (Asia/Atlantis, 121 chars, lower(trim) collision), test_a_stale_version_is_409_and_writes_nothing, test_no_create_and_no_delete_route_and_both_answer_405_from_the_global_handler, test_a_hall_without_cinema_id_is_422_and_never_defaulted. Red-proof: with check_version disabled, test_a_stale_version_is_409_and_writes_nothing went red. Then the check was restored.

**Note:** EP-ADM-28/29 live in backend/app/api/admin/cinemas.py and backend/app/domain/admin/cinemas.py. The items also carry showtime_count, as EP-ADM-28 specifies.

### S-ADM-05 — Done

**Evidence:** backend/tests/adm/test_s_adm_05.py, 6 passed ('......'). The tests cover: 201 with is_active true, has_showtimes false, version 1 and one screen.created row; duplicate and case-variant names refused with count unchanged; trimmed lengths 0 and 61 give 422 and 60 gives 201; rename gives version+1 and screen.updated, and also works on a hall that has showtimes; the list carries every field, in name order; there is no DELETE route, and DELETE answers 405 with 'That action is not available. Nothing was changed.' with screen count unchanged.

### S-ADM-06 — Done

**Evidence:** backend/tests/adm/test_s_adm_06.py, 9 passed ('.........'). The tests: test_a_batch_of_500_is_201_and_501_is_422; the C12/C13/C14 fixture checks duplicate_labels in submitted order, the plural sentence, and that nothing is written; the singular C13 case; coordinate collisions give the singular sentence and '3 of those positions'; each field bound has its own sentence; row_label is stored upper-trimmed, 'I' is allowed, and non-ASCII gives 422 (JC-R6-03); PATCH and DELETE before any showtime write seat.updated and seat.deleted; GET seats comes back in drawing order with has_showtimes and showtime_count; test_a_seat_write_waits_on_the_screen_row_lock (pg_locks granted=false for the app backend pid = 1, then the insert completes 201). The 220-seat / 220 seat.created clause is backend/tests/adm/test_s_adm_02.py::test_a_220_seat_batch_writes_220_seat_created_rows_one_per_seat (passed). Red-proof: with .with_for_update() removed from lock_screen, the lock test went red. Then it was restored.

**Note:** The lock test's holder takes FOR SHARE, not FOR UPDATE. A FOR UPDATE holder also blocks the foreign-key check's FOR KEY SHARE, so the test passed even with the app's lock removed. That was observed, and the test was strengthened.

### S-ADM-07 — Done

**Evidence:** backend/tests/adm/test_s_adm_07.py, 7 passed ('.......'). The tests: test_frozen_fields_and_delete_are_409_with_their_sentences_and_no_audit_row (row_label, seat_number, seat_category_id, DELETE; details keys exactly screen_id, seat_id, showtime_count, frozen_fields; audit count unchanged); test_in_the_same_state_grid_service_add_and_rename_stay_permitted; test_a_past_unbooked_showtime_freezes_exactly_like_a_future_sold_out_one; test_a_future_sold_out_showtime_refuses_identically (bodies equal apart from request_id and ids); test_the_domain_function_raises_layout_frozen_with_no_http_request; test_the_check_is_not_in_the_handler (rg showtime_count|LAYOUT_FROZEN over api/admin = 0); test_exactly_one_route_accepts_row_label_and_it_is_patch_seat. Red-proof: with the freeze condition disabled, 3 tests went red. Then it was restored.

**Note:** LayoutFrozen is in backend/app/domain/admin/halls.py.

### S-ADM-08 — Done

**Evidence:** backend/tests/adm/test_s_adm_08.py, 5 passed ('.....'). The tests: test_the_sequence_501_to_504 (90/91/90, restoring J11 leaves 503 at 90, 504 = 91, 501 = 90 throughout, PATCH changes neither count, census query = 0); test_zero_seats_in_service_is_409_and_no_showtime_is_written; test_both_unique_indexes_exist_by_name_and_are_different_jobs; test_no_route_edits_a_seat_set_and_such_addresses_are_404 (POST /showtimes/501/seats and DELETE /showtimes/501/seats/77 give 404 'That page does not exist.'); test_a_failing_seat_set_insert_is_503_and_leaves_no_showtime.

**Note:** The test caught a real bug: the async driver reports rowcount -1 for INSERT ... SELECT, so seat_count_at_creation came out as -1. Fixed by counting RETURNING rows. uq_showtime_seat__showtime_id_seat_id exists by name in information_schema, but its constraint_type is PRIMARY KEY, not UNIQUE: PostgreSQL folded the duplicate UNIQUE into the PK and kept the unique's name (observed). See doc_defects.

### S-ADM-10 — Done

**Evidence:** backend/tests/adm/test_s_adm_10.py, 5 passed ('.....'). The tests: test_overlap_is_409_and_the_zero_gap_and_later_creates_are_201 (exact sentence 'Screen 3 already has a showtime from 6:30 pm to 8:58 pm on 4 Sep 2026...', conflicts array with exactly 4 keys and naive local times, 20:58-22:53 gives 201); test_c_at_21_15_is_201_and_two_conflicts_give_an_array_of_two; test_the_edit_predicate_excludes_its_own_row_as_captured_from_the_statement (a before_cursor_execute capture: the edit SQL carries 'showtime.id !=' and the create SQL does not); test_two_concurrent_overlapping_creates_produce_one_201_and_one_409 (count +1); test_no_changeover_minimum_exists_anywhere. Red-proof: with the predicate made closed (<=, >=), the zero-gap test went red. With the screen lock removed, the concurrency test went red. Both were restored.

### S-ADM-01 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_01.py, 7 of 8 passed. Passing: the role matrix (401/403/403/200) on GET /api/admin/screens; require_admin in every /api/admin route's resolved dependant; the mounted /api/admin set equals exactly the 20 Phase 2 endpoints of contract.json (EP-ADM-09..24, 28, 29); the rg pattern and AST string-literal checks find 0; manager-router methods are a subset of GET/HEAD; a role UPDATE gives 403 on the next request. RED: test_the_403_does_not_reveal_whether_the_object_exists. The bodies are equal, but the message is 'This account does not have access to that page.' rather than P-ADM-18's sentence.

**Note:** Blocked for two reasons. (1) GET /api/admin/movies and 8 other routes (EP-ADM-01..08, 25..27) are Phase 6 (S-ADM-21..28). The 29-route count cannot hold until then. (2) require_admin in backend/app/api/deps.py (foundation, not owned) raises FORBIDDEN with the registry default. P-ADM-18 needs 'This page is for administrators. Your account cannot change films, showtimes, prices or halls.' The fix is one line in deps.py: require_admin passes that message. It cannot be done from api/admin without breaking test_s_xct_10's router-dependency assertion.

### S-ADM-02 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_02.py, 10 of 11 passed. Passing: the audit_log columns and FK; POST screens writes one screen.created row with null before, the admin as actor and request_id = X-Request-Id; a forced audit failure gives screen count unchanged and 500 with the exact sentence quoting X-Request-Id; AuditAction is a closed StrEnum equal to the P-ADM-19 table parsed from E6_admin.md (39), and AuditAction('screen.exploded') raises ValueError; a non-member action fails before BEGIN (listener: the only statement is the router dependency's users SELECT; counts unchanged); as frontrow_app, UPDATE and DELETE give 42501 while SELECT and INSERT succeed; 220-seat batch = 220 seat.created rows; the two-change/one-change split (cinema analogue); user rows have 7 fields and no credential keys; JFIF/card query = 0; actor_user_id NULL = 0. RED: the rg showtime[.]price_changed check hits backend/app/domain/audit.py:7, a foundation docstring that names the forbidden string in order to forbid it.

**Note:** Blocked for two reasons. (1) The movie title + display_until clause needs EP-ADM-04 (Phase 6). (2) The rg clause fails on the foundation's own docstring in domain/audit.py. Reword it, e.g. 'not showtime DOT price_changed'. Interpretation: 'zero statements for that request' is read as zero statements by the handler. The router's require_admin must read the user row first (role-from-row), and that one SELECT is unavoidable.

### S-ADM-04 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_04.py, 3 passed. test_no_request_path_code_names_cinema_timezone: 0 hits under api, domain, models, workers, jobs and frontend/src; the only backend/app hit is core/config.py. test_the_row_zone_wins_over_the_variable_and_a_zone_change_rewrites_no_instant: with CINEMA_TIMEZONE=UTC and the row at Asia/Kolkata, 14:00Z renders 2026-08-14T19:30:00 and /health/ready is 200; after PATCH to Asia/Dubai the stored starts_at is identical and it renders 18:00. test_no_zone_column_on_showtime_or_screen.

**Note:** Blocked on clauses outside this lane. The boot WARNING lines (mismatch and unseeded), the boot statement listener, and 'CINEMA_TIMEZONE unset exits non-zero' belong to app/main.py lifespan and app/core/config.py (foundation). config.py gives CINEMA_TIMEZONE a default of 'Asia/Kolkata', so 'unset' cannot exit non-zero as written. 'Hits in exactly config.py and scripts/seed.py' needs the seed lane.

### S-ADM-09 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_09.py, 9 passed. Covered: naive local in and out (18:30 is stored as 13:00:00Z and 20:58 as 15:28:00Z); Z, +05:30, a zone name and a bracketed zone give 422 with the table unchanged; a draft film gives 201; a past start gives 201; out-of-service gives 409 with its sentence; zero seats give 409; unknown film or hall gives 404; ends = starts and ends one minute earlier give 422; an inactive format gives 422; outside the display window gives 422 with showtime, showtime_seat and audit_log counts unchanged; a null window accepts any start; the screen-lock wait test (red-proofed); no worker or job inserts a showtime and no scheduler pattern exists; ends_at is unchanged by a runtime change.

**Note:** Blocked for three reasons. (1) The rg 'INSERT INTO showtime|Showtime[(] hits exactly three files' cannot pass as written. The code uses SQLAlchemy Core insert(showtime), which the pattern does not match. It names backend/app/domain/showtimes.py, while the ledger's OwnedPaths put the domain at backend/app/domain/admin/. It also needs scripts/seed.py (seed lane). The test asserts instead that insert(showtime) appears only in backend/app/domain/admin/showtimes.py. (2) 'A showtime already carrying a withdrawn format_id still returns it on a GET' needs the browse GET (Phase 3), because EP-ADM-09 items carry no format_id. (3) The runtime PATCH needs EP-ADM-04 (Phase 6). It is proved via a direct UPDATE.

### S-ADM-11 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_11.py, 8 passed. Covered: one row per kind of change, and both changes give two rows; a different screen_id gives 422 with its sentence and audit unchanged; merged-row bounds (starts 20:58, starts 21:30, ends 18:30 each give 422) with seat set and seat_count unchanged; overlap on the merged interval excluding itself; booking_seat.price_paise identical after editing a booked showtime; the 601-604 day fixture at the injected 13:05:00Z (include_past absent/true gives all four, false gives only 604); exactly the query params screen_id, date, include_past; the 422/404 sentences; rg datetime.now()|utcnow|time.time() outside core/clock.py = 0.

**Note:** Blocked only on 'a customer holding seats when the start moves still holds them, asserted by the hold token in Redis'. Holds are Phase 4. This lane writes no Redis code, so the edit cannot touch a hold. That is reasoned, not observed.

### S-ADM-12 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_12.py, 5 passed: 25000.5, '25000', 0 and -1 give 422 with their sentences and nothing stored; missing gives 'Enter a base price for this showtime.'; 1 gives 201; the column is bigint; 691770197019033 gives 201 and ...034 gives 422 at highest uplift 3333; with 6666 stored, ...033 gives 422; contract.json EP-ADM-10/11 carry the literal; rg [*/]\s*100\b over backend/app = 0; 2500000 gives 201 and seat_price_paise(2500000,1250) = 2812500. Frontend: node --test frontend/src/features/admin/money.test.mjs gives 3 pass, 0 fail. showtimeBody({rupees:'250.00'}) yields base_price_paise 25000 as an integer, and the conversion is by string/BigInt, not float.

**Note:** Blocked for three reasons. (1) MINOR_UNIT_RATIO and CURRENCY_CODE are specified in backend/app/core/money.py. The foundation put them in config as CURRENCY_MINOR_UNIT_RATIO/CURRENCY_CODE, and app/domain/money.py holds the strict types. That is a foundation/doc decision. (2) 'Capturing the body the form submits' is proved only for the body-building function the form calls, not by rendering the form. No frontend test runner (vitest, jsdom) is approved. (3) The seat-map GET price is Phase 3.

### S-ADM-13 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_13.py, 4 of 5 passed. Passing: 25000/28125/33333, 24999 at 3333 = 33331, and 3 x 33333 = 99999; uplift -1 and 1250.5 give their sentences; a 4th category gives 201; a lower(trim) name collision gives 422; with exactly one showtime at 25000, 368934881464190 gives 201 and ...191 gives 422, and at 50000 ...190 gives 422; name + uplift give two rows; DELETE is unmounted and answers 405. backend/tests/adm/test_s_adm_13_count.py, 3 passed: +15 gives 3 at 09:00:00Z; -15 gives 1; GET 3 then a clock advance of 600s, then PATCH gives 2 with evaluated_at_utc 09:10:00Z and no warning key. RED: test_the_formula_file_holds_no_float_decimal_half_literal_or_standard_special_case.

**Note:** Blocked on backend/app/domain/pricing.py (foundation, not owned). The rg '[.]5' hits its docstring '33332.5'. Its constants are _BASIS_POINTS_PER_WHOLE = 10_000 and _HALF_UP, not BASIS_POINT_SCALE and BASIS_POINT_HALF with bare literals 10000/5000 as the AC requires. Fix: rename the constants and reword the docstring.

### S-ADM-14 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_14.py, 6 passed: version columns are exactly movie, showtime, screen, seat_category, cinema; the PATCH seat body model has no version; every Phase 2 form GET returns version; no version gives 422 with the out-of-date sentence; stale gives 409 with the row and audit unchanged; the order cases (stale + identical gives 409, current + 61 chars already stored gives 422, all-identical gives 200 with the row byte-identical, version not bumped and no audit row); two fields with one changed give one row naming that change; seat is_active same gives 409 while an unchanged grid_row gives 200 with no audit row. Red-proof: with check_version disabled, 2 of these tests plus S-ADM-03's stale test went red. Then it was restored.

**Note:** Blocked for two reasons. (1) The poster multipart version clause needs EP-ADM-05 (Phase 6). (2) The 'five admin edit forms submit the GET's version' clause needs a frontend test runner (not approved), and SCR-ADM-02 is Phase 6. The four Phase 2 forms (VenueScreen, HallsScreen, CategoriesScreen, ShowtimesScreen) do send version from the GET, but this is not proved at runtime.

### S-ADM-16 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_16.py, 4 passed: deactivated/reactivated rows carry exact before/after; a repeat gives 409 'Seat C12 is already out of service.' / '... in service.'; the screen-row lock wait test (red-proofed: removing the lock turned it red); an existing showtime keeps the retired seat (counts identical), booking_seat for the seat is unchanged, a showtime created while out excludes it, and reactivation does not add it back; no route path has a cancel or refund segment.

**Note:** Blocked only on 'GET /api/me/bookings/{reference} still renders the original row_label and seat_number'. That is the account lane, Phase 4. The seat row is asserted unchanged.

### S-ADM-17 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_17.py, 2 passed: withdraw gives 200 with version+1 and screen.deactivated, reactivate gives screen.reactivated; showtime, seat and booking_seat counts are unchanged; POST showtime on the withdrawn hall gives 409 with the exact sentence; stale gives 409 with audit unchanged; there is no DELETE route and DELETE gives 405 with the generic sentence and screen count unchanged; the SCR-ADM-05 confirmation text is present byte-for-byte in frontend/src/features/admin/HallsScreen.tsx (static check).

**Note:** Blocked on clauses owned elsewhere: GET /api/me/bookings (Phase 4) and GET /api/reports (Phase 8). Conflict: this AC's required copy '...and nothing is refunded...' makes tests/xct/test_s_xct_42.py (rg refund over frontend/src) go RED, and also breaks S-ADM-20's 'exactly two copy lines'. See doc_defects.

### S-ADM-18 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_18.py, 11 passed. Covered: one-transaction create (role manager, a bcrypt digest that fullmatches $2b$..., password_version 1, last_signed_in_at null, 2 assignments, manager.created + 2 manager.screen_assigned, outbox unchanged); login with any password gives 401 CREDENTIALS_INVALID with the exact sentence (through the account lane's POST /api/auth/login); two managers have different hashes; a role property gives 400 with users unchanged; replaying every POST/PUT under /api/admin with role admin leaves the admin count unchanged, and rg role\s*=\s*.admin. over backend/app and migrations = 0; the exact refusal sentences; PUT diff with the unassigned row's entity_type, entity_id = the removed PK, before {user_id, screen_id}, after null, the row gone, and no FK on audit_log.entity_id; a repeat PUT writes nothing; a non-manager gives 422 with its sentence, nobody gives 404; the unique constraint exists by name, 0 CHECKs, 0 triggers, and a 3rd manager on one hall gives 201; list ordered by email with derived has_signed_in and no such column; no credential keys in any audit row.

**Note:** Blocked on two clauses. (1) The manager dashboard returning 200 with an empty rows array is Phase 8. (2) 'The SES test double records zero calls': no SES code exists until Phase 5. Only the outbox_message count is asserted.

### S-ADM-19 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_19.py, 5 passed: exactly one DELETE under /api/admin (/api/admin/seats/{seat_id}); DELETE on showtimes/{id}, screens/{id} and cinemas/{id} gives 405 with the generic sentence, and the bodies are equal without request_id; delete( targets in backend/app are only seat and manager_screen_assignment (msa); zero CASCADE FKs, and delete_rule is in {RESTRICT, NO ACTION}; the rg for retention/prune/purge/cron/... = 0. test_the_phase_6_addresses_do_not_exist_yet records that DELETE /api/admin/movies/1 and /lookups/... currently answer 404.

**Note:** Blocked for two reasons. (1) DELETE on /api/admin/movies/{id}, /lookups/{kind} and /lookups/{kind}/{id} can only answer 405 once those paths are mounted for another method (Phase 6, S-ADM-21..28). (2) The byte comparison of GET /api/me/bookings/{reference} is Phase 4.

### S-ADM-20 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_20.py, 6 passed: no DELETE on a showtime path, no POST ending in /withdraw or /cancel, and no body model with a withdrawn/cancelled/status field; a PATCH carrying withdrawn_at, cancelled_at or status gives 400 REQUEST_INVALID with the exact sentence and the row unchanged; no such showtime columns, while booking keeps status and cancelled_at; POST .../601/withdraw, .../601/cancel and /api/admin/no-such-address give identical 404 bodies; the SCR-ADM-03 standing text is present in frontend/src/features/admin/ShowtimesScreen.tsx with no Withdraw/Cancel/Delete control text; cancelled_at = 0 hits in api, domain and frontend/src.

**Note:** Blocked for two reasons. (1) The 'refund appears on exactly two published copy lines' clause needs the SCR-TKT-01 line (Phase 4) and the receipt template (Phase 5). It conflicts with S-ADM-17's required SCR-ADM-05 copy, which is a third 'refund' line. (2) The cancelled_at census names backend/app/models/booking.py, but the foundation's ORM mirror is backend/app/models/__init__.py. 'Renders no control' is a static source check; no frontend runner exists.

### S-ADM-29 — Blocked

**Evidence:** backend/tests/adm/test_s_adm_29.py, 1 passed: the movie table has no provenance, attribution, source, license, licence or credit column.

**Note:** Almost every clause belongs to other lanes. The seed's titles, names and single poster asset belong to scripts/seed.py (seed lane). POST /api/admin/movies is Phase 6 (S-ADM-23). GET /api/movies/{id}/poster 302 is Phase 3.

### S-SCP-06 — Blocked

**Evidence:** backend/tests/scp/test_s_scp_06.py, 2 of 4 passed: rg cinema_?staff|door_?scanner|ticket_?validat = 0; no Pydantic model under app/ declares a field named role. RED: test_the_role_enum_has_exactly_the_four_values (no Role enum exists under app/). RED: test_register_with_a_role_property_is_400_request_invalid. POST /api/auth/register with role 'staff' currently returns 201: the account lane's register accepts the unknown property instead of refusing it.

**Note:** Blocked on the account lane (E-ACC). It must add a Role enum (guest, customer, manager, admin) and make register reject unknown properties with 400 REQUEST_INVALID. The test finds the enum wherever it is defined under app/.

## p2-seed-scope (verifier verdict: PASS_WITH_DEFECTS)

### S-SCP-04 — Done

**Evidence:** backend/tests/scp/test_s_scp_04.py (5 tests: booking columns, table names, users columns, password_reset_token.used_at exempt and present, the patterns watched matching what they refuse) against a DB built by the real `migrate` entrypoint command. Run: `docker compose --profile test run --rm test python -m pytest ... tests/scp/test_s_scp_04.py` -> `tests/scp/test_s_scp_04.py .....` inside `102 passed in 265.17s`.

**Note:** All four clauses asserted against alembic upgrade head on an empty database.

### S-SCP-05 — Blocked

**Evidence:** backend/tests/scp/test_s_scp_05.py (3 tests, all pass: booking.status + cancelled_at nullable/no default; count(*) FROM cinema = 1 after the seed; screen.cinema_id NOT NULL FK -> cinema(id)) -> `tests/scp/test_s_scp_05.py ...` in `102 passed`.

**Note:** Three of four assertions proven. Blocked on: GET /api/reference cinemas length 1. That is EP-BRW-07, built by the Phase 3 browse lane (S-BRW-05). app/api/browse.py mounts no route yet. No red test was added.

### S-SCP-07 — Blocked

**Evidence:** backend/tests/scp/test_s_scp_07.py (7 tests, all pass): route walk finds no DELETE under /api/admin/showtimes and no withdraw/cancel path; DELETE /api/admin/showtimes/1 -> 405 METHOD_NOT_ALLOWED; POST .../1/withdraw -> 404 NOT_FOUND; PATCH with status, withdrawn or cancelled_at -> 400 REQUEST_INVALID; source-level scan of ShowtimesScreen.tsx button text and aria-labels finds no withdraw|cancel|delete|pull -> `.......` in `102 passed`.

**Note:** Blocked on two clauses. (1) error.details must name the rejected property, but app/domain/admin/common.py submitted() raises ApiError(400,'REQUEST_INVALID') with no details. That file belongs to the admin lane, and the fix is to pass details listing sorted(body.model_extra). (2) The rendered accessibility tree: the repo has no browser harness, so only the weaker source-level check exists.

### S-XCT-43 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_43.py (7 tests, all pass): the no-'production' regex over the 7 deployed paths returns 0; COOKIE_SECURE declared with no default, and `python -m app api` exits non-zero naming it when it is unset; COOKIE_SECURE=true with an http base URL exits naming both; seeded DB has 0 non-DEMO movies and 0 non-.invalid users; no ?token=/access_token=/Bearer and no localStorage; no self-signed/openssl req; no .pem/.crt/.key file; P2_TLS_CERTIFICATE.md carries all five literal steps and the Zone C sentence -> `.......` in `102 passed`.

**Note:** Blocked on one clause: the TLS spec must be found through the Spec cell of the AWS_PREP_QUEUE.md row whose Item contains 'TLS certificate' (row 14). That cell is still an em dash and the queue file is outside this lane. Needed edit: link [`P2_TLS_CERTIFICATE.md`](P2_TLS_CERTIFICATE.md) in row 14's Spec cell. The key-file check walks the filesystem instead of `git ls-files`, because the test image has no git. The walk is a superset of tracked files, so it is stricter.

### S-XCT-44 — Blocked

**Evidence:** scripts/seed.py + backend/tests/xct/test_s_xct_44.py (18 tests, all pass, oracle = expected_summary.json): DEMO CINEMA/Asia/Kolkata; six screens matching rows/cols/labels/seat counts; no I and Screen 1 rows A..H J; unique labels with A1/A10/J20 present; bands computed via seed.bands() and read back per band (Screen 1 = 50/30/10); prices 24999/28124/33331 via seat_price_paise; 11 DEMO lookup rows; 8 published films inside their windows with count(DISTINCT poster_object_key)=1; DEMO MOVIE 04 = LANGUAGE A, RATING 2, GENRE 4+1; 0 unreferenced lookup rows; a bad layout exits non-zero naming SCREEN 2 with every table unchanged; no http(s):// in seed, no faker/mimesis/factory_boy, no card-shaped number -> `..................` in `102 passed`. Red-proofed: re-allowing I and using float ceil made 3 tests fail.

**Note:** Blocked on: (1) the poster written through app.domain.posters (`rg -c 'from app.domain.posters import' scripts/seed.py` returns 0). That module is the Phase 6 poster upload (S-ADM-25) and does not exist. The seed records a fixed key for a committed asset and uploads nothing. (2) GET /api/movies non-empty, and the rendered landing page not showing 'Nothing is showing right now.' Both are Phase 3 browse-lane work that does not exist yet.

### S-XCT-45 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_45.py (15 tests, all pass, figures read from expected_summary.json): 720 showtimes at 11:00/14:30/18:00/21:30 IST, timestamptz; no YYYY-MM-DD in seed.py; 360 before / 360 from today against the injected clock; 8 films x 90; runtimes 90..160; ends_at = start+runtime+20 with the 21:30/160 case at 00:30; max occupancy 180 min; 0 overlaps; formats 360/360; k=231 worked example (DEMO MOVIE 01, 126 seats, ends 19:50); occupancy in 1..n-1 and contiguous from A1; 58,800 seats, 11,003 bookings, 220/221 per customer, size histogram, 115,200 showtime_seat rows, takings 1,511,815,400; every non-null oracle table count; payments captured; dispatch suppressed/attempts 0/null timestamps; 12 oracle invariants run verbatim; all 11,003 references valid; a second run with the clock moved 3 days inserts nothing and keeps every showtime's movie_id; the interrupted-run plan equals the stored schedule -> `...............` in `102 passed`. Red-proofed: ignoring existing showtimes made the second-run test fail.

**Note:** Refuted by the verifier: The AC clause 'the seed enqueues no receipt job, asserted by the queue's message count being 0 after the run' is not exercised. The test substitutes `count(*) FROM outbox_message WHERE topic='receipt.send' = 0`. The lane disclosed this. The argument that a queue would then be empty is reasoned, not observed, because no queue exists in Phase 2. This is why the row is refuted as Done: every other clause is proven.

### S-XCT-46 — Done

**Evidence:** backend/tests/xct/test_s_xct_46.py (9 tests, all pass): audit_log 0 after a fresh seed, 0 null actors, 0 users off SEED_EMAIL_DOMAIN, 0 non-DEMO movies; NOTICE printed exactly once and before the first `INSERT INTO showtime` in the captured SQL trace, with nothing printed earlier; first INSERT order language/certification/genre/format < screen < seat < movie < showtime; no input(/sys.stdin, and a subprocess run with stdin=DEVNULL exits 0 with 720 showtimes; with insert_vocabulary patched to a no-op the seed exits non-zero, movie count is 0 and every table is unchanged; a second run leaves all 22 table counts unchanged and keeps a hand-changed password_hash; --help lists --wipe-and-reseed; the wipe sentence, 'Settle seat labelling...' and '409 LAYOUT_FROZEN' are in docs/30 Deployment/P2_SEED_TASK.md; PATCH label, PATCH category and DELETE on a seeded seat each return 409 LAYOUT_FROZEN; a sweep of all 12 mounted /api/admin POST/PATCH/PUT/DELETE routes adds exactly +1 audit_log row each, and the walk fails if a write route has no request in the sweep -> `.........` in `102 passed`. Red-proofed: a doubled NOTICE and a non-idempotent showtime pass each turned their test red.

**Note:** --wipe-and-reseed is also exercised (owner URL; edited row gone; 11,003 bookings again).

### S-XCT-48 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_48.py (13 tests, all pass): absent, empty, 11-character, 25-Devanagari (75-byte) and .env.example-placeholder values each exit non-zero, print the bound or name, print no warning, and leave every table unchanged; the placeholder is refused by value (seed.PASSWORD_PLACEHOLDER equals the .env.example line); seed.hash_password is app.core.security.hash_password, a counting wrapper records exactly 1 call at BCRYPT_COST, and count(DISTINCT password_hash)=1 across 63 users; addresses are deterministic at demo.frontrow.invalid; stdout carries admin: 1 / manager: 12 / customer: 50 with the addresses and never the password; the manager->screen mapping is floor((m-1)/2)+1; POST /api/auth/login works for admin-01 (200 + fr_session cookie) and for all 50 customers -> `.............` in `102 passed`.

**Note:** Blocked on clauses outside this lane. (1) `rg -n 'SEED_DEFAULT_PASSWORD' backend/app` currently hits backend/app/core/config.py (SeedSettings, SEED_PASSWORD_PLACEHOLDER, load_seed_settings), which the foundation lane owns. The seed no longer imports any of it, so it can be deleted, but S-XCT-29 ties .env.example names to config.py (see doc_defects). (2) The repo-wide `rg -nP '\$2[aby]\$\d\d\$' .` hits backend/tests/dbkit.py:30 and backend/tests/acc/test_s_acc_10.py:38 (literal '$2b$04$'). Neither is this lane's file; splitting each literal (e.g. "$2b$" + "04$") would fix it. 'No file written' is checked only by a static scan of seed.py (no open()/write_text/write_bytes).

### S-XCT-49 — Blocked

**Evidence:** backend/tests/xct/test_s_xct_49.py (3 tests, all pass): docs/30 Deployment/P2_SEED_TASK.md carries every required literal (a one-off ECS task; a task definition family that is the seed's alone; the same image; run once and deliberately by the client; /frontrow/<environment>/SEED_DEFAULT_PASSWORD; SecureString; valueFrom; the execution role, not the task role; the never-carries sentence; the admin-01@ acceptance criterion); AWS_PREP_QUEUE.md has exactly one 'one-off seed task' row needed by Phase 2; no register-task-definition/ssm put-parameter/iam create|attach|put/ecs run-task in the 5 scoped paths -> `...` in `102 passed`.

**Note:** Blocked on Zone B and doc edits outside this lane. (1) backend/entrypoint.sh has no `seed` command, so the `seed` branch, its exit status and 0 'seed' hits in the api/worker branches are untested. (2) The image cannot run scripts/seed.py anyway: the Docker build context is ./backend and the runtime stage copies only app/ and migrations/. scripts/ must be moved into the context or the context changed (foundation lane). (3) Row 19's Spec cell still reads '(owed by the Phase 2 goal...)' and must link [`P2_SEED_TASK.md`](P2_SEED_TASK.md). The queue file is not this lane's.

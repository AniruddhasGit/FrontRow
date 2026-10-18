# SIT harness — what it must provide for these cases to run

```
Produced by ....... GOAL_10 (goals/GOAL_10_sit.txt), compressed per SRC-004 R-1
Status ............ SPECIFICATION. No harness code exists. Writing it is Phase 1 work, not this goal.
Read with ......... ../FIXTURES.tsv · ../SIT_TestCases.tsv · ../SIT_JourneyCases.tsv
```

> **Nothing here has been run.** No application code exists yet. Each requirement below is what a case
> in this folder assumes. A case whose requirement is missing cannot run. It does not fail; it just
> produces no result, and that is worse than failing.

Each requirement has an id. Cases and defects cite it.

## H-01 · Fixture loading

- Load any fixture in `../FIXTURES.tsv` by its id, in its `BuildsOn` order. Before every case, reset to
  that fixture:
  - `TRUNCATE … RESTART IDENTITY CASCADE` on every application table, run by the harness role and
    never by the application role
  - `FLUSHDB` on the test Redis database
  - purge the ElasticMQ queues
  - clear the recording mail stub
- `FX-30-CELL` inserts the rows that a case's `Precondition` lists, using the ids given there. Primary
  keys are `GENERATED ALWAYS AS IDENTITY` (`docs/06 DataModel/AGENT_CONTRACT.md` rule 5), so the
  builder must use `OVERRIDING SYSTEM VALUE` and then advance each identity past the highest id it
  inserted. Without that step, the next insert by the application collides.
- Users are created through the application's own registration and admin functions. A
  password hash is never written by hand. No fixture contains card data of any shape (`CLAUDE.md`).
- A path placeholder such as `{id}` that a case does not name binds to the lowest id among the
  matching rows of `FX-20-SEED`. The case's Precondition says so.

## H-02 · Clock injection

- The application reads time through one clock port. The harness pins it to the case's `ClockInstant`
  and moves it forward only when a clause says to (`T0+181s`). **Nothing calls `sleep`.** No case reads
  the wall clock (`CONSTITUTION.md` Art IX.5).
- The only database defaults that call `now()` are `created_at` and `updated_at` (FR-ADR-018). They
  carry no decision. A clause that compares one of them with the injected clock is a defect in that
  clause. It is not something the harness should paper over.
- **Redis TTLs run on Redis's own clock**, and the injected clock does not move them. A clause about
  expiry either uses the Redis test double it names (as `S-ADM-15` does), or asserts `PTTL` within a
  tolerance. The harness must offer both.

## H-03 · One authenticated client per role

The harness provides these clients:

- `guest`: no cookie, no `Authorization` header
- `customer` A and B
- `manager` M and M2
- `admin`

All of them come from `FX-10-ACCOUNTS`. Each one signs in through `POST /api/auth/login` and holds
the `fr_session` cookie. No client mints a token, and no client uses a test-only bypass: `S-XCT-17`
greps for exactly that. The stress script signs in its own fifty customers (`stress01..stress50`).

## H-04 · Forcing a Redis failure

There are two modes, because they fail differently:

- **refused**: `docker compose stop redis`. Connections are refused immediately.
- **hung**: `docker compose pause redis`. The connect and command timeouts fire, because the
  `REDIS_*_TIMEOUT_MS` settings are what bound the wait.

For both modes, the case asserts a 503 with `DEPENDENCY_UNAVAILABLE` on the hold paths. Browsing
still returns 200 from PostgreSQL wherever the PRD says it does, and `/health/ready` returns 503
while `/health/live` returns 200 (`S-SEA-15`). **The harness never makes the lock path fall back to
the database.** The case checks that no fallback happens.

## H-05 · SIGTERM in the middle of a request

1. Hold a confirm request open on purpose by setting the simulated payment delay port
   (`PAYMENT_SIMULATED_DELAY_MS`) for that one request.
2. Send `docker kill --signal SIGTERM` to the API container.
3. Assert all of the following:
   - new connections are refused
   - the in-flight request either completes or rolls back whole, with no half-written booking
   - this instance's Redis locks are released
   - the process exits within the drain window (`SRC-002 §7.5`)

## H-06 · Statement capture

The harness installs a SQLAlchemy `before_cursor_execute` listener for one request. It also offers
PostgreSQL `log_statement=all` capture for that request's backend.

Cases that need it: `S-ACC-08`, `S-ACC-13`, `S-TKT-02`, `S-RPT-09`.

The listener sees **parameterised** SQL. A clause that looks for a literal value inside that SQL must
read the bound parameters instead.

## H-07 · Shared-connection mode

Only `S-XCT-13` needs this. That case sums `pg_stat_xact_user_tables` across every GET route.

The view reports only the calling transaction. For the sum to mean anything, the harness must bind
the application's session to the test's own connection and transaction. Without that binding, the
sum is 0 however broken the code is (the `harness-dependent` row for `S-XCT-13` in `BIBLE_DEFECTS_SIT.tsv`).

## H-08 · Queue and mail inspection

- Receive from ElasticMQ without deleting the message, so a case can read the raw body. Cases that
  need this: `S-ACC-07`, `S-TKT-05`, `S-TKT-15` and `S-XCT-25`. Under `SRC-004 R-3` the reset
  message body carries the token, so the stub must also record the request's own direct send and be
  able to make that send fail on demand (`S-ACC-07`, `SRC-004 JC-R6-01`).
- A recording mail port that stores every `SendEmail` call as parsed MIME (`S-SCP-15`).
- Redeliver one message on demand, for the idempotent-send cases.

## H-09 · Log capture

The harness captures the API's and the worker's JSON stdout at `DEBUG` for the whole of a request.
It asserts that no secret, password, reset token or card-shaped string appears in that output.

`SRC-004 R-3` adds a requirement: the queue payload field that carries the reset token is **redacted
by the logger**.

## H-10 · Static inspection

- The harness can import the FastAPI `app` without starting a server. It needs this to walk
  `app.routes` and to read the OpenAPI document.
- ripgrep searches run with the scopes that each clause states.
- **A search never covers the test module that issues it.** This is census defect class 1
  (`docs/05 Bible/CENSUS_2026-08-22.md`).

## H-11 · The deployed run

- Clauses that name the deployed environment change `--base-url` and nothing else. The harness sends
  only HTTP and creates nothing in AWS.
- Until the client runs it, every result from the deployed environment is **reasoned, not observed**.

## Wall-clock exceptions the harness cannot remove — filed, not waived

These cases measure real time:

- `S-XCT-01` and `S-SEA-18`: the spread of request start times, which shows the fifty requests
  really were concurrent
- `S-XCT-17`: a warm-up band of about ten minutes against the real login limiter

All three run as specified. The no-wall-clock rule still applies to them, though, so they are filed
as the three `wall-clock-measurement` rows of `BIBLE_DEFECTS_SIT.tsv`. Making an exception to the rule is the client's call: it
counts as waiving a quality check, which is reserved to the client.

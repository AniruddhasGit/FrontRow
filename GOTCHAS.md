# GOTCHAS — hard-won traps (symptom → root cause → fix)

Read this **before** building, not after debugging. Append every trap you hit, in this shape.
A trap recorded once is cheaper than the same trap found twice.

Entries marked **[UNPROVEN HERE]** were found by reading, or carried forward from `SpendWise`, the
prior project on this method. They are believed true and **have not been observed failing on
FrontRow** — which under `CONSTITUTION.md` Art VII.1 is exactly the distinction that matters.

**As of 2026-08-14 every entry below is `[UNPROVEN HERE]`.** No application code exists yet, so
nothing on this project has sprung a trap. When one does, move it out of the carried-forward
sections and write what actually happened.

---

## Concurrency and seat locking — the failure class this project exists to prevent

- **A `SETNX` without a TTL is a permanent seat lock.** A process that crashes between acquiring the
  lock and releasing it leaves the seat unbuyable forever, and no test catches it because tests
  release cleanly. *Fix:* set the TTL **in the same command** as the acquisition (`SET key val NX PX
  ttl`), never as a second call — a crash between the two calls produces the same permanent lock.
  [UNPROVEN HERE]

- **Releasing a lock you no longer own deletes someone else's lock.** User A's lock expires, user B
  acquires the same seat, then A's abandoned tab fires its release and frees B's seat while B is
  paying. *Fix:* the token in `SRC-002 §8.1.3` is not decoration. Release is a **Lua script** that
  compares the token and deletes atomically. A `GET` then `DEL` in two calls has the same race.
  [UNPROVEN HERE]

- **`SELECT ... FOR UPDATE` on rows that do not exist locks nothing.** Two transactions both find no
  booking for `(showtime, seat)`, both proceed, both insert. The row-level lock cannot protect a row
  that is not there. *Fix:* the **unique constraint** is the real guard (`SRC-002 §8.1.5`); the
  `FOR UPDATE` only serialises contention over rows that already exist. Catch the unique violation
  and translate it into the "someone took that seat" error `SRC-001 §5.2.6` requires. [UNPROVEN HERE]

- **A test that proves the lock works does not prove the constraint works.** With Redis healthy the
  database guard never fires, so a missing unique constraint passes every normal test. *Fix:* the
  red-proof in `CLAUDE.md` — drop the constraint, run the stress script, watch two winners appear.
  A guard nobody has watched fail is decoration. [UNPROVEN HERE]

- **50 concurrent requests from one Python process is not 50 concurrent requests.** A stress script
  using a single event loop, one connection pool, or `requests` in a thread pool will serialise
  enough that the race never happens and the test passes against genuinely broken code. *Fix:* make
  the script prove its own concurrency — assert the spread between first and last request start time
  is small — before trusting its result. [UNPROVEN HERE]

## Database & Postgres

- **Local Postgres gives you superuser; RDS never does.** A migration that works in the local
  container fails on RDS. *Fix:* build against the restricted role from day one. The three places
  they differ: superuser, forced SSL, and the allowed extension list. [UNPROVEN HERE]

- **Alembic does NOT take an advisory lock.** Widely believed, not true. Two ECS tasks booting
  together race on `alembic upgrade head`. On this project `SRC-002 §7.8` requires migrations to be
  a separate step anyway, which removes the race — **that is the reason for the rule**, not a
  stylistic preference. [UNPROVEN HERE]

- **`db.t3.micro` has roughly 110 maximum connections.** Two uvicorn workers × pool size × N tasks,
  plus the worker container, plus your own `psql`, adds up faster than it looks. *Fix:* size the pool
  deliberately; do not accept the default and hope. [UNPROVEN HERE]

- **`SUM()` of a `bigint` column returns `numeric`**, which arrives in Python as `Decimal` and then
  either fails to serialise or mixes badly with `int`. *Fix:* cast to `BigInteger` in the query.
  Relevant here for revenue and occupancy totals. [UNPROVEN HERE]

## Redis

- **A Redis connection failure inside an `except` block is the second outage.** Code that catches a
  lock failure and then tries to log to Redis, or read a cached seat map to build the error message,
  fails again inside the handler. *Fix:* the failure path touches nothing that can fail.
  [UNPROVEN HERE]

- **Cache-aside on a hot seat map is a stampede waiting to happen.** The TTL expires on a popular
  Friday showtime and every in-flight request rebuilds the map at once. `SRC-002 §8.2.3` requires the
  place this could happen to be documented **in code**, with what prevented it. *Fix:* a per-key
  rebuild lock, or a stale-while-revalidate window. Whichever is chosen, write down which.
  [UNPROVEN HERE]

- **ElastiCache `t3.micro` is one node with no replica.** There is no failover. Art IV.6 says the
  seat-hold path must return an error rather than fall back, so a Redis restart is a visible partial
  outage by design. That is intended; do not "fix" it. [UNPROVEN HERE]

## Money & time

- **Floats cannot hold 0.10.** Summing them drifts. *Fix:* integer minor units everywhere; `Decimal`
  only at the parsing boundary; format for display at render time only. [UNPROVEN HERE]

- **The currency is not ruled yet** (`OPEN-LOCALE-01`). A minor-unit ratio hardcoded now is
  effectively permanent, because `SRC-001 §7.6` makes booking records historical and reinterpreting
  the unit later silently rewrites what past customers paid. *Fix:* configuration from the first line
  of schema. [UNPROVEN HERE]

- **"Showtime" is a timezone question, and a cinema is a physical place.** A showtime stored without
  a zone, or evaluated in UTC on the server, is wrong by the offset at both ends — and "sales close
  20 minutes before the show" then closes at the wrong moment. `SRC-001 §10.4` has not named a
  country. *Fix:* store an instant plus the cinema's zone; never let the server infer "today" from
  its own clock. [UNPROVEN HERE]

- **A test that reads the wall clock goes red at midnight with no code change.** On the prior project
  four assertions failed this way. *Fix:* inject time. Art IX.5 makes this a defect, not a nuisance.
  [UNPROVEN HERE]

## Web & auth

- **A rate limiter storing state in-process multiplies its own limit.** With two workers across N
  tasks, "5 attempts per 15 minutes" is really 5 × 2 × N. `SRC-002 §8.4.1` requires the token bucket
  in **Redis**, which avoids this — but only if every process actually uses it. [UNPROVEN HERE]

- **A rate limiter behind a load balancer limits the load balancer.** Its default key is the peer
  address, which behind an ALB is the ALB — so every customer shares one bucket and the limiter
  appears to work while protecting nothing. *Fix:* `--proxy-headers` with an explicit
  `--forwarded-allow-ips`, and key on the real client address. **`SRC-002 §8.4.1` requires per-user
  AND per-IP**, so getting the IP wrong silently halves the design. [UNPROVEN HERE]

- **bcrypt blocks the event loop.** Roughly 300 ms of pure CPU inside an `async def` stalls every
  other request on that worker. On a shared 1 GB host a handful of simultaneous logins is a visible
  outage. *Fix:* `asyncio.to_thread`. Also: **bcrypt silently truncates at 72 bytes** — reject or
  pre-hash, do not ignore it. [UNPROVEN HERE]

- **An idempotency key stored after the work is done is not idempotent.** Two simultaneous retries
  both check, both find nothing, both book. *Fix:* insert the key with a unique constraint **first**,
  in the same transaction as the booking; the loser reads the winner's result. [UNPROVEN HERE]

## Deployment & operations

- **A health check that touches the database makes a database blip restart every container.** That is
  precisely why `SRC-002 §7.4` splits them: `/health/live` must not touch a dependency, `/health/ready`
  must. Wiring the ALB or the ECS task definition to the wrong one turns a recoverable dependency
  outage into a restart loop. This is a Zone C configuration decision, so **the specification in
  `docs/30 Deployment/` must say which endpoint goes where and why.** [UNPROVEN HERE]

- **With one EC2 instance and a fixed host port, two tasks cannot run at once**, so ECS's default
  deployment configuration deadlocks waiting for a healthy new task that can never start. *Fix:*
  minimum-healthy-percent 0, and accept a hard downtime window on every deploy. Owed as advance
  notice under Art VIII.4. *(reasoned, not observed)* [UNPROVEN HERE]

- **Container stdout dies with the container unless a log driver is configured.** With the default
  driver, the record of a crash loop is destroyed by the restart that caused it. `SRC-002 §5.4.5`
  requires JSON to stdout; **something has to collect it**, and that is a Zone C item that needs a
  prep-queue row. [UNPROVEN HERE]

- **SIGTERM without lock release strands every seat that instance was holding** for the full TTL.
  A deploy during a Friday evening rush would make a block of seats unbuyable for seven minutes with
  no error anywhere. `SRC-002 §7.5` requires the release; this is what it is for. [UNPROVEN HERE]

- **No NAT Gateway means a private subnet has no outbound internet.** TMDB, S3, SQS and SSM all need
  egress. The application must run in a public subnet with strict security groups (`§5.4.4`), and
  every outbound dependency must be written down. [UNPROVEN HERE]

## Process traps

- **A check that cannot fail looks exactly like a clean result.** *Fix:* `.gitattributes` with
  `* text=auto eol=lf` at the repository root, **and** red-proof every gate — plant a violation,
  watch it fire, revert, verify the revert. [UNPROVEN HERE]

- **A requirements document can state a false fact with total confidence.** Three did on the prior
  project. *Fix:* verify load-bearing technical premises before they become specification. A premise
  inherited without checking is a bug with a long fuse. [UNPROVEN HERE]

- **An assumption in a question becomes a requirement in the next document.** Already happened here:
  `SRC-001 §10.9` asks "how long should seats be held? We assumed 7 minutes", and `SRC-002 §8.1.1`
  then states 7 minutes as a fixed requirement. **The client's open question was answered by the
  client's own next paragraph, and nobody ruled it.** That is `OPEN-HOLD-01`. *Fix:* when a number
  appears in a specification, find the ruling that produced it. If the only source is an assumption,
  it is `ASSUMED`, not `RULED`. **This is the one trap already confirmed present on FrontRow.**

- **The client and the builder being one person removes the delay that catches bad answers.** There
  is no queue to make visible when the decider is also at the keyboard. *Fix:* every irreversible
  question gets a fresh zero-context second opinion before it is acted on. [UNPROVEN HERE]

- **A blanket "you decide everything" instruction quietly repeals the constitution.** *Fix:*
  technical calls are the session's; reserved matters stay reserved; reversible reserved matters get
  decided-then-batched for reversal rather than blocking. [UNPROVEN HERE]

- **Parallel pytest against one shared database deadlocks on per-test truncation.** The prior project
  hit a genuine `DeadlockDetectedError` this way and no agent could get a clean full run. *Fix:* a
  per-worker database, or a lock. Do not parallelise the suite against one database. [UNPROVEN HERE]

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

## Checks that measure less than they appear to

Four separate instances on 2026-08-14/15, in four unrelated files. **This is the project's most
frequent defect shape so far.**

- **`contrast.py` reported eleven PASS lines against zero data.** No tokens existed; the checks
  measured nothing and said so in green. Only one check failed, and it alone held the exit code.
  *Fix:* a check whose subject set is empty reports `SKIP` or `FAIL`, **never `PASS`**, and prints
  its subject count. Vacuous truth is not a pass.
- **A prep-queue rule reported `14 of 14` while four new rows sat outside the table it parsed.**
  A blank line had split one markdown table into two. The count was true of what it read.
- **Five published `Retry-After` strings passed a rendering check and were all wrong.** Correctly
  formatted — real integers, right unit, right plural — and not one derivable from its bucket.
  Four were the bucket's capacity; one was its window. *The lesson, from the PRD:* **the format is
  the cheap half; the derivation is the half that is wrong in practice**, and a review stopping at
  the first has confirmed nothing.
- **A `SRC-003` summary table said 34/5/1 while its own per-row tags said 36/3/1.** Both totalled
  40, which is why it survived a day and a 70-record ADR pack.

**The standing rule that came out of it: a count or a figure stated in prose is a claim, and it is
derived from the file or it is wrong.**

## A claim corrected in prose is not corrected in the generator input

`E6_admin.md`'s `FORBIDDEN` block declared *"no DELETE route is mounted"* while listing
`EP-ADM-21` — a mounted `DELETE` — in its own `raised_by` array, in the same JSON object. It
survived that lane's own correction pass, because the pass was reading P-row exception tables and
this is a fenced generator block. **The machine-readable copy is the one that reaches the artifact.**
When correcting a factual claim, grep for it in the generator inputs too.

## Three columns on `password_reset_token`, and collapsing any pair has a name

`email_claimed_at` (a worker holds this job, cleared on failure) · `email_sent_at` (an email went
out, **never** cleared) · `used_at` (the customer spent the token).

Reusing `email_sent_at` as the claim looks like the minimal fix and **sends a second password reset
link** after a redelivery, because a stale check reclaims a row whose email already went out. A
duplicate credential email is worse than the lockout it was fixing. [UNPROVEN HERE — found in
specification, no code exists]

## A control specified in complete detail can still have no words

Three independent screen sweeps across the PRD found **40 controls named with no published string**
— including a filter group where none of four controls had a label, a retry action that had tokens,
behaviour and a rule about its accessible name but no text anywhere, and an HTML anchor with a URL
and no link text. **Every gap sat inside a row that read as thorough**, which is why none was found
by reading. *Rule:* a screen that names a control owes that control's words; the only discharges are
publishing the string or deferring by name to the row that does.

## Fan-out lanes that cannot reach their coordinator

On `GOAL_05` the coordinator could message any lane by id, but **no lane could reach the coordinator
or each other** — six `SendMessage` attempts by one lane all failed with "no agent reachable". Every
lane report therefore arrived only as its **final message**, relayed by hand through the main
session, with a delay of one full wave.

Three costs, all observed:

- **Stale re-flags.** Lanes re-reported defects that had been fixed one or two waves earlier — one
  item was raised three times after it was corrected. A lane cannot see another lane's fix, so it
  re-reports from its own last read.
- **Cross-lane findings arrive late.** A lane finding a defect in a file it does not own can only
  report it at the end of its turn. Three separate lanes flagged something the coordinator needed
  *during* the wave, not after it.
- **It forces the coordinator into the lane's file.** With a correction sitting behind a relay and a
  file apparently idle, the main session edited a section directly — and produced exactly the defect
  write-set discipline prevents: a **partial fix that contradicted itself**, leaving a sentence one
  paragraph below still framed the way the paragraph above had just withdrawn. The lane owning the
  file caught the concurrent write between two reads seconds apart, stopped rather than clobbering,
  and completed the fix properly.

*Fix:* give every lane the coordinator's agent id in its brief, explicitly, and say that
cross-lane findings are messaged **when found**, not held to the final report. **A partial fix by a
non-owner is worse than a late fix by the owner**, because the original text was at least
internally consistent.

## A brief is not a warrant

Two lanes were handed the same sentence for a security rationale: *"a 43-character token is
brute-forceable at line rate."* **It was false** — the token is 32 bytes from a CSPRNG, a 2²⁵⁶
space, so an attacker gets ~1.8 × 10⁶ guesses in its lifetime, which is indistinguishable from zero.

One lane **refused to write it** and produced the honest rationale instead. The other **published it
and withdrew it later**, after a second reader ran the arithmetic. Its own conclusion is the rule:

> *"The wording came from the brief but I published it, and Art VII.1 binds the writer."*

*Fix:* a brief that hands you a **factual assertion inside a rationale** — a number, a threat model,
a performance claim — is something to verify **before** publishing, not after. Refusing at the point
of writing is the better outcome; withdrawing later is acceptable; publishing and leaving it is not.

**And an invented rationale is self-defeating, not merely wrong.** The first engineer who checks the
arithmetic concludes the control is unnecessary and removes it — so a false reason for a real
control is more dangerous than no reason at all.

## Internal consistency masks external falsity

A worked example stated a password was **25 code points / 75 bytes**. The real string is **28 / 84**.
It survived **eight review passes** — and the reason is the useful part: `25 x 3 = 75`, so the two
halves agreed with each other perfectly. **Nothing inside the sentence contradicted itself.** Only
the literal sitting beside it disagreed, and no reader compared them.

It had also propagated into **five published copy strings** telling a customer *"the limit is 72
bytes and yours is 75"*.

*Fix:* a check that a statement is self-consistent is not a check that it is true. Where a figure
describes a literal that is present, **compute it from the literal** — `len(s.encode("utf-8"))` —
rather than reading the sentence for plausibility. And a figure a customer sees about their own
input is **interpolated, never typed**.

## A table assembled by reading for a shape claims a completeness it never had

Three separate sections did this on one project, and each then stated or implied that its list was
the complete set:

- a wrong-retry-string table built by reading for numbers, which **missed a fourth instance**
- a date-format audit built by reading for date-shaped strings, which reached over four sites
- a claim that one arithmetic defect was *"the only arithmetic defect in the document"*, retracted

**A reader scanning for a shape finds what the reader looked at.** That is a sample, not an
inventory, and it is not a substitute for walking the file.

*Fix:* derive the list mechanically where the shape is machine-detectable — parse the blocks,
enumerate the endpoints, compute the counts. Where it genuinely cannot be derived, **say the list is
what was found, not what exists.** A table that names its own method is honest; one that implies
exhaustiveness it never earned is worse than a shorter list.

## A worked example whose inputs do not exercise the rule it demonstrates

The PRD's example for the price-rounding rule used base `25000` paise and a `1200` basis-point
uplift. `25000 x 11200 = 280,000,000`, which **divides by 10,000 exactly** — so the `+5000` half-up
term did nothing, and the example produced the same answer with the rounding rule and without it.

**It demonstrated nothing, and it would pass every check anyone would think to run**, because the
arithmetic in it was correct. Only the *purpose* was unmet. A reviewer verifying the numbers
confirms the numbers; nobody asks whether the numbers could have been produced by the wrong rule.

The replacement uses the seeded figures — `24999 x 11250 = 281,238,750`, exact quotient
`28,123.875` — so the term fires and the answer is `28124` rather than `28123`.

*Fix:* an example that exists to demonstrate a rule must be **checked against the rule's absence**.
Compute it with the rule and without it; if the two agree, the example is decoration. This applies
to every worked example that carries a rounding step, a boundary, a cap, or a tie-break.

**The general form, which this project met four separate ways:** a check that cannot fail, a count
that describes a smaller world than it appears to, a table that claims a completeness it never had,
and now **an example that cannot distinguish the rule from its absence.** In every case the artifact
was internally correct and externally useless.

## Record which properties were designed and which fell out

A seed's idempotency anchor was written to read the earliest existing row rather than the clock, so
a second run inserts nothing. **It also repairs an interrupted run** — but that second property was
never designed; it fell out of the first. The lane wrote it down **as luck rather than as
foresight**, on the ground that *the next reader deciding whether to change this should know which
parts were reasoned.*

That is the useful rule. A document that presents an accidental property as an intended one makes a
future reader preserve the wrong thing — or, worse, refactor away the accident while carefully
keeping the part that never mattered.

The same lane's other note generalises further and is worth carrying: after correcting a figure it
re-checked the three claims that leaned on it. Two were unaffected and one was *confirmed* by the
correction. **None of that was knowable in advance** — and a correction that stops at the figure is
only a correction if the dependents happen to be fine, which is not a state anyone can assert
without looking. **The check that feels redundant is the one that establishes the thing being
assumed.**

## A killed agent's file can be intact and its work still lost

Three agents died mid-goal on `GOAL_05` — two connection losses, one 600-second stall. **Every file
was perfectly intact**: balanced fences, every block parsing, complete final sentences, all gates
green. The write-then-think cycle means a kill lands in the gap between writes rather than inside
one.

**So a file-integrity check cannot see the damage, because there is none. The damage is absence.**

Worse, the obvious recovery is also wrong. Both the coordinator and the main session recovered
**what each dead turn had announced in prose** — *"Now doing X"* — and verified those. One lane
later re-derived its assignment from the original brief and found **four** unwritten items, not the
two it had announced. Its own conclusion:

> *"What a dead turn announced is not what it was assigned. The only reliable recovery input is the
> original brief's assignment list."*

An agent announces an item when it starts it, so anything assigned-but-not-reached was never spoken
and is invisible to a reader of the transcript.

*Fix:* on any agent failure, recover against **the brief**, not the transcript. Re-derive the full
assignment list and check each item against the file. Treat the last announcement as the *floor* of
what is missing, never the extent of it. And note that the readers caught some of these as guesses —
**a spec gap from a lost turn is indistinguishable, to a reader, from a spec gap that was never
written**, which is the only reason they surfaced at all.

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

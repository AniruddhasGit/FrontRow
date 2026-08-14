# The merge pass — dedupe, and the cross-lens contradiction hunt

```
Run ........ 2026-08-14, GOAL_02
Inputs ..... lens-1-data-shape.md · lens-2-concurrency.md · lens-3-money-and-time.md
             lens-4-user-visible.md · lens-5-operations.md
Method ..... five independent sub-agents, each reading SRC-001 + SRC-002 + SRC-003 in full
             including both §E sections, with no sight of each other's returns
Output ..... 70 records, FR-ADR-001 … FR-ADR-070
```

> **Why the lenses were run blind.** Two lenses resolving the same question differently is the defect
> class this method exists to catch. If they can see each other they converge, and the disagreement —
> which is the signal — disappears. **Zero contradictions would have been a suspicious result, not a
> good one.** Nine were found.

---

## 1 — Volume

| | Lines returned |
|---|---|
| Lens 1 — data shape | 87 |
| Lens 2 — concurrency | 83 |
| Lens 3 — money and time | 57 |
| Lens 4 — user-visible | 99 |
| Lens 5 — operations | 118 |
| **Raw total** | **444** |

After deduplication across lenses, **70 distinct decisions** justified a record. The compression is
mostly the ruled items: `SRC-003 OPEN-BOOK-01`'s ten-seat cap was returned independently by four of
the five lenses, and the 3-minute hold by all five.

---

## 2 — Cross-lens contradictions

**Nine found.** Each is recorded with both sides and where it was resolved. A contradiction here is
not a lens being wrong — in most of these both lenses read the same clause correctly and the clause
does not determine the answer.

### X-1 · Does `SRC-002 §7.9` cover all of Redis, or only locks?

**Lens 2** — `OPEN`: "Whether Redis unavailability also fails the browse and seat-map read path, or
only the hold and booking write path."
**Lens 4** — `RULED`: "When Redis is unreachable the user sees an error, never a silently degraded seat
map."
**Lens 5** — `RULED`: "If Redis is down the application returns an error and never falls back to the
database for locks."

Lens 4 generalised `§7.9` to the whole seat map. Lens 5 kept it to locks. Lens 2 said the scope was
undecided. **All three read the same sentence.** The clause says "do not silently fall back to the
database **for locks**", and Redis does three jobs here.

**Resolved in `FR-ADR-028`:** locks fail loudly, the cache degrades to PostgreSQL, the rate limiter
fails closed. Lens 5's reading of `§7.9` is correct; lens 4's user-facing conclusion is wrong for
browsing and right for holding.

### X-2 · Does `/health/ready` returning 503 on Redis loss make X-1 moot?

**Lens 2** — `OPEN`: "Whether `/health/ready` returning 503 on Redis loss pulls every instance out of
the ALB and thereby takes down read traffic too" (`§7.4` vs `§7.9`).
**Lens 5** — `RULED`, stated flatly: readiness returns 503 when Postgres or Redis is unreachable.

Lens 5 recorded the clause; lens 2 saw the consequence. With one EC2 instance, a Redis outage removes
the only instance from the ALB, so browsing is down regardless of what the application would have
served.

**Resolved in `FR-ADR-028`:** `§7.4` is followed exactly and **the consequence is recorded rather than
softened**. The cache behaviour still matters because readiness is polled on an interval and a partial
Redis failure is not instant.

### X-3 · Is a hold persisted in PostgreSQL?

**Lens 1** — `RULED`: "Seat holds live only in Redis with a config-driven 3-minute TTL and have no
Postgres table."
**Lens 2** — `OPEN`: "whether a hold is persisted at all is undecided", and separately whether expiry
is evaluated against Redis TTL or a stored `held_until`.
**Lens 3** — `OPEN`: "Whether Redis TTL or a database timestamp is authoritative for expiry."

**Lens 1 over-read.** `SRC-002 §8.1.4` says expiry needs no cleanup job; it does not say a hold has no
row. Two lenses correctly found it open.

**Resolved in `FR-ADR-025`:** no hold table, Redis TTL is the sole authority. That is lens 1's answer
— reached as a build-session judgment call under Art III.9, **not** as a ruled fact, which is the
distinction that matters.

### X-4 · Is the rounding rule decided?

**Lens 4** — `RULED`: "Per-seat price is base price plus a fixed category uplift, **with the rounding
rule visible in totals**."
**Lens 3** — `OPEN` + `RESERVED`: "The exact rounding mode… is not stated anywhere — only that a rule
must be written", plus a second open line on per-seat versus per-total.
**Lens 1** — `OPEN`, treated as a data-shape question.

**Lens 4 is wrong.** `SRC-003 OPEN-PRICE-01` explicitly defers the rounding rule to be stated with a
worked example. Lens 3 also caught the second dimension — per seat or per total — that lenses 1 and 4
missed entirely, and it is the one that changes the answer by more than a paisa.

**Resolved in `FR-ADR-038`:** integer half-up, per seat, never the total, with four worked examples.
Filed as reserved-but-reversible and batched for client reversal.

### X-5 · Is the price snapshot a data question or a money question?

**Lens 1** — `OPEN`, data shape: "Whether the price actually charged is snapshotted onto each
booked-seat row or recomputed."
**Lens 2** — `OPEN`, concurrency: "Whether the price is captured at hold time or recomputed at confirm
time."
**Lens 3** — `OPEN` + **`RESERVED`**: "Whether the paid amount is snapshotted… so a later base-price
edit cannot rewrite what a past customer paid."

Not a disagreement about the answer — **a disagreement about who may decide it.** Lens 3 classed it
reserved; lenses 1 and 2 treated it as technical.

**Resolved as stricter-wins:** snapshotting is the conservative option and Art III.10 makes adopting
it need no signature. `FR-ADR-039` files it as `STRICTER_ADOPTION`, and `FR-ADR-035` covers the hold
half that lens 2 found.

### X-6 · Is the queue technology settled?

**Lens 2** — treated it as settled: SQS with a DLQ, `RULED`, and never raised the library question.
**Lens 5** — `OPEN`: "The mandate both prefers RQ or Dramatiq over Celery (`§5.4.1`) and specifies a
worker consuming SQS (`§4.5`); which library, if any, sits over the queue interface is unresolved."

`SRC-003 OPEN-QUEUE-01` settles the **broker**. It says nothing about `§5.4.1`'s library preference,
which is still live text in a frozen source with no erratum against it. **A contradiction of
completeness:** lens 2 declared closed what lens 5 found still open.

**Resolved in `FR-ADR-059`:** no task-queue library at all, with `§5.4.1` read as scoped to *which*
library if a Redis-brokered queue were used. The reading is recorded because anyone reading `§5.4.1`
alone will reach a different conclusion.

### X-7 · Does SIGTERM lock release contradict expiry needing no cleanup?

**Lens 5** — `OPEN`, naming it as a contradiction: "`§7.5` vs `§8.1.4`… which behaviour wins for a
customer mid-checkout is unresolved."
**Lens 2** — `RULED` on the shutdown sequence, then **three separate `OPEN` lines** on how a stateless
instance knows which locks are its own, whether live holds are dropped, and the grace period.

Lens 2 accepted the clause and found its unimplementable parts. Lens 5 named the clause-level
conflict. **Both correct; the clause cannot be implemented literally without deciding something.**

**Resolved in `FR-ADR-033`:** expiry is the correctness guarantee, shutdown release is an optimisation
on top of it, and a per-instance registry in Redis — not in process memory, which `§7.3` forbids —
makes "locks held by that instance" knowable.

### X-8 · Is the poster upload mechanism settled?

**Lens 4** — `RULED`: "Posters are uploaded by the admin to S3 and served from our own URLs, never
hotlinked."
**Lens 5** — `OPEN`, twice: whether upload is a presigned PUT or a multipart POST, and whether serving
is public-read, presigned or proxied — noting that `§7.3` forbids buffering to local disk.

Lens 4 recorded the ruled outcome and read it as settling the mechanism. It does not.

**Resolved in `FR-ADR-061`:** multipart POST streamed to a private bucket, served by 302 redirect to a
presigned URL, with the local-development gap stated rather than hidden.

### X-9 · Is `SRC-002 §11`'s flat `docs/` layout live?

**Lens 5** — `PROVISIONAL`: "The mandate's flat `docs/deployment-tasks.md`, `docs/decisions.md` and
`docs/runbook.md` paths conflict with the repository's numbered folders, and the mapping is not
recorded."
**Every other lens** — silent.

Not a disagreement between two answers but a **single-lens catch the other four missed**, and it
matters: `§13.5` requires unspecified decisions to be recorded in `docs/decisions.md`, a file that does
not exist. A future session either creates a competing decision register or ignores a clause.

**Resolved in `FR-ADR-008`.**

---

## 3 — Where a single lens caught something the other four missed

Recorded because it is the argument for running five rather than two.

| Lens | The catch | Record |
|---|---|---|
| 3 | Rounding is **two** questions — the mode, and per-seat versus per-total | `FR-ADR-038` |
| 5 | `§7.7` requires a Prometheus endpoint and nothing in the approved stack can scrape it | `FR-ADR-057` |
| 5 | `CONSTITUTION.md` Art VIII.13's outbound list still names TMDB | `FR-ADR-065`, raised |
| 4 | The customer's **own** held seats are a fourth seat-map state nobody specified | `FR-ADR-045` |
| 2 | Two multi-seat holds with overlapping seats can deadlock without a deterministic order | `FR-ADR-026` |
| 1 | A screen's layout being edited after bookings exist breaks the oversell guard's key | `FR-ADR-022` |
| 5 | Nothing watches the dead letter queue, so a failed receipt is invisible | `FR-ADR-068` |

---

## 4 — Stale clauses in `CONSTITUTION.md`, found by the sweep and **not fixed**

`CONSTITUTION.md` is outside this goal's write-set, and Art XII.1 makes amending it reserved to the
client. **Three live clauses contradict `SRC-003` and are raised, not corrected:**

| Clause | What it says | What is true now |
|---|---|---|
| **Art I.6** — win condition | "a booking reference **and a scannable ticket**… movie data arrives **from TMDB on a schedule** and appears only after an admin publishes it" | No scannable ticket (`SRC-001 §E E-9`). No TMDB and no schedule (`SRC-001 §E E-4`, `SRC-002 §E E-2`, `§E E-4`) |
| **Art V.8** — refunds | "`OPEN-CANCEL-01` and `OPEN-CANCEL-02` **are open**" | Both were `RULED` on 2026-08-14 — no refunds, no cancellation |
| **Art VIII.13** — outbound paths | "**TMDB**, S3, SQS and SSM at minimum" | TMDB is gone; the real list is S3, SQS, SES, SSM, ECR and CloudWatch Logs (`FR-ADR-065`) |

Art I.6 is the most consequential: it is the project's stated **win condition** and it describes two
features that no longer exist.

---

## 5 — What the sweep found that stays open

Four reserved questions were surfaced and **none was ruled**. Each has a record that decides nothing
and names who must decide it: `FR-ADR-007` (`OPEN-ATTRIB-01`), `FR-ADR-023` (`OPEN-SHOWCANCEL-01`),
`FR-ADR-049` (`OPEN-EMAILFAIL-01`), `FR-ADR-069` (`OPEN-TLS-01`).

**No new Article X row is proposed.** Every reserved question the sweep found maps onto one of the
four rows that already exist in `CONSTITUTION.md` Article X.0. That is a real result and not an
absence of looking — the four rows raised by `SRC-003` turned out to cover the reserved surface the
five lenses found.

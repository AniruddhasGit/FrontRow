# FrontRow Project Constitution

| Field | Value |
|---|---|
| Version | `frontrow-constitution@0.1.0` — v0.1-draft |
| Decision status | **NOT_DECIDED** (fail-closed — binds nothing until ratified) |
| Release status | NOT_RELEASED |
| Ratifier | the client — exact name pending `OPEN-NAME-01` |
| Drafted | 2026-08-14, from `docs/00 SourceOfTruth/SRC-001` and `SRC-002` |
| Governs | the FrontRow build and the use of this repository |
| Method lineage | The AI-SDLC method proved on `SpendWise` (`github.com/AniruddhaDynpro/SpendWise`). Where FrontRow diverges from that project's conventions, the divergence is stated in the clause, never left silent. |

---

## Preamble

This is the single short document of **non-negotiable principles** for FrontRow. Every
specification, plan, ADR, backlog row and implementation is checked against it.

**It invents nothing.** Every binding article consolidates a rule that already binds — from the
frozen sources `SRC-001` and `SRC-002`, or from an `APPROVED` row in the ADR ledger — and cites
where it came from. Where a decision is still open, Article X lists it as open and deliberately does
not decide it.

This document is a **gate, not a spec.** The cited sources carry the full detail.

**A standing note on this project's shape.** One person is the client, the developer, the
money-signer and the rules-signer. That weakens the method's central control: the decision queue
never forms when the decider is also at the keyboard. The compensating control is Article IX.7 — a
fresh zero-context session grades every irreversible call.

### Reading rules

- **MUST / MUST NOT** items bind on ratification.
- **(build-session ruled)** items were decided by the build session under the standing technical
  delegation. They bind, and the client may reverse any of them at any time.
- **(unverified)** marks a claim the build session has not observed. Under Article VII it may never
  harden into a `MUST`.
- **(reasoned, not observed)** marks any statement about AWS runtime behaviour. Article VIII.3
  explains why every such statement carries this label on this project.

---

## Article I — Scope

1. **The functional envelope is `docs/00 SourceOfTruth/SRC-001` plus the ADR records in
   `docs/01 ADR/all-ADRs/` as governed by the ledger.** No user-facing functionality beyond those
   two locations. Per Art XI.1 **the ledger, never this sentence, is the count of record** — stated
   as a location rather than a number so this clause cannot go stale.
   Envelope ≠ approval: Article III still controls what is approved to *build*.
2. **Hard exclusions** (`SRC-001 §6`) MUST NOT enter scope: no native mobile application; no food
   and beverage ordering; no loyalty points or membership tiers; no multi-language interface; no
   integration with an existing point-of-sale system.
3. **Excluded is not blocked** (`SRC-001 §6.6`). The client may ask for any of the above later, so
   no design decision may foreclose them. An exclusion that hardens into an architectural
   impossibility is a defect against this clause.
4. **The build order is `SRC-002 §12`, seven phases, and it is the client's**, not the build
   session's. A phase closes only when the client has been told what to test (`SRC-002 §12.1`).
5. Any "can it also…" request is a **scope change only the client decides.** A reviewer, a test run
   or a fresh agent cannot authorise scope.
6. **Win condition — define victory, then stop.** A guest browses current movies, picks a cinema and
   a showtime, sees a live seat map, selects seats, holds them, pays through the simulated provider,
   and receives a booking reference and a scannable ticket; **fifty concurrent requests for one seat
   produce exactly one winner, proved at the database layer**; movie data arrives from TMDB on a
   schedule and appears only after an admin publishes it; and it runs on AWS from containers the
   client deployed by hand. Everything past that line is fast-follow.
7. **The purpose of this project is stated in `SRC-002 §1.3` and binds the design**: the application
   must be shaped so that deploying it teaches the client DevOps. Where two designs are equally
   correct and one forces the operator to confront a real infrastructure concern, **that one is
   chosen**, and the reason is recorded.

## Article II — Authority Order & Sources

1. **On conflict, resolve in this order:** raw `SRC-001` wording → raw `SRC-002` wording → an
   explicit client ruling (`SRC-003`, when it exists) → an `APPROVED` ADR → `03 PRD` → `02 BRD` →
   `05 Bible` → everything else. **Stricter always wins.**
2. **Where `SRC-001` and `SRC-002` conflict, neither silently wins.** `SRC-001` is the client
   speaking as the cinema operator about *what the product does*; `SRC-002` is the same person
   speaking as the developer about *how it is built*. A conflict between them is a genuine
   contradiction in the client's own instructions and MUST be raised as an Article X row, never
   resolved by the build session picking a favourite. Known conflicts at drafting: payment
   (`SRC-001 §5.3.1` requires it, `SRC-002` never mentions it), the role set (`SRC-001 §4` names
   five, `SRC-002 §3.1` names one), cancellation (`SRC-001 §5.4.3` requires it, `SRC-002 §12` has no
   phase for it), management reporting (`SRC-001 §5.5.2` requires it, `SRC-002 §12` has no phase for
   it), and the queue technology (`SRC-002 §4.5` says SQS, `SRC-002 §5.4.1` prefers Redis brokers).
3. `SRC-001` and `SRC-002` are **frozen inputs.** They MUST NOT be edited. The only permitted
   modification is a clearly-marked `ERRATUM` block appended at the foot.
4. **Errata govern over the text they correct.** They are enumerated in each source's `§E`. None
   exist as of 2026-08-14.
5. **Fingerprints are the evidence of record.** `docs/00 SourceOfTruth/fingerprints.json` holds a
   SHA-256 per frozen source. If a hash changes, every artifact derived from that source is
   **invalidated and MUST be re-derived**, never silently reused. Verify with
   `sha256sum -c fingerprints.sha256`, under Git Bash — a CRLF working copy will not reproduce the
   hashes.
6. **A hash comparison is the weaker guarantee.** It proves a file was not edited; it cannot see a
   requirement the file never contained. Where a document is marked `GENERATED`, the stronger check
   regenerates it and compares content.
7. **Derived content MUST cite a source or carry an explicit `ASSUMED` flag.** `ASSUMED` is
   inference, never authority, and MUST NOT be promoted into a `MUST` rule.
8. Superseded text MUST be **marked superseded where it stands.** An unmarked contradiction between
   two live documents is a defect, not a reader's judgement call.
9. **The originals stay.** `CLIENT_ASK.md` and `CLAUDE_CODE_BRIEF.md` remain in the repository root
   exactly as the client handed them over. Nothing cites them. Every citation points at the `SRC`
   files, because those are the hashed ones.

## Article III — Decision & Release Governance

1. The decision authority of record is **`docs/01 ADR/ADR_DECISION_RELEASE_LEDGER.tsv`**. Decisions
   are **fail-closed**: every new ADR starts `NOT_DECIDED` + `HOLD_PENDING_DECISION` +
   `NOT_RELEASED`. **Silence never counts as approval, retirement, or release.**
2. ADR ids take the form `FR-ADR-nnn`, zero-padded to three digits, allocated in filing order and
   never reused.
3. Accepted decisions are **immutable.** A reversal happens by a new superseding record, never by
   editing history. The superseded record is retained unedited and marked.
4. **A supersession is itself a claim, and it gets checked.** A record that claims to supersede
   another must be verified to actually do so; a link that resolves is not the same as a link that
   is true.
5. The ledger's four `included_in_*` columns are the **anti-drift mechanism**: a decision is not
   merely decided, it must be shown to have *landed* in the BRD, PRD, Bible and data model. Flip a
   cell to `INCLUDED` only with the carrying section cited in `notes`, and derive the cell **from
   the citations actually present in each target**, never by assertion.
6. **Credentials MUST NEVER appear in an ADR, the ledger, or any committed file.**
7. **Status law**, applied to every schema, API and specification artifact:

   | Status | Meaning |
   |---|---|
   | `RULED` | decided, with a citation to a frozen source or an `APPROVED` ADR |
   | `PROVISIONAL` | written down, a ruling still outstanding |
   | `OPEN` | genuinely unruled — **escalate, never invent** |
   | `ASSUMED` | inference; never hardens into a constraint |

8. **Reserved matters — no model decides these, at any confidence.** Money · anything irreversible
   or public · secrets · legal and data protection · amending this Constitution · what the product
   is and what "done" means · scope changes · **waiving any quality check** · anything marked
   `[HUMAN]`. **No timeout defaults past a reserved matter** — if the approver is unavailable, that
   work stops.
9. **Standing technical delegation.** The build session decides technical questions that are not
   reserved, and logs each as one `[JUDGMENT CALL]` line in the handoff. Reversible reserved matters
   are decided and then **batched** for the client to reverse. Reserved-and-irreversible stops and
   waits.
10. Adopting a **stricter** option is not a waiver and needs no signature.

## Article IV — Correctness & Concurrency Floors

> This is FrontRow's central article. `SRC-001 §2.2` calls eliminating double-booking
> "non-negotiable" and `§7.1` says a seat sold twice is a failure of the whole system regardless of
> load. Everything here exists to make that testable rather than hoped for.

1. **A seat MUST NOT be sold twice, under any load, ever** (`SRC-001 §2.2`, `§3.2`, `§7.1`).
2. **The guarantee is enforced twice, in two different systems.** A Redis lock provides the *hold*;
   a database constraint provides the *truth*. Either alone is insufficient and does not satisfy
   this article.
   - **Redis** (`SRC-002 §8.1`): a lock per `(showtime, seat)` with a TTL, acquired **atomically**,
     carrying a **token** so a client can only release a lock it owns, expiring with no cleanup job.
   - **PostgreSQL** (`SRC-002 §8.1.5`): a **unique constraint on `(showtime_id, seat_id)`** plus
     `SELECT ... FOR UPDATE` or optimistic locking, so that **Redis being wrong cannot oversell**.
3. **The database guard is the one that may not be waived.** Redis is a cache and a lock service;
   losing it must degrade the product, never corrupt it.
4. **The concurrency proof is a deliverable, not a claim** (`SRC-002 §9.1`): `scripts/stress_seats.py`
   fires 50 simultaneous requests for one seat and asserts exactly one succeeds. It MUST run against
   local Docker and against the deployed environment by changing a base URL.
5. **Red-proof the guard.** The unique constraint is dropped on purpose, the stress script is watched
   producing more than one winner, the constraint is restored, and the restore is verified. **A gate
   nobody has watched fail is decoration.**
6. **Fail loudly on dependency loss** (`SRC-002 §7.9`). If Redis is unreachable the seat-hold path
   returns an error. It MUST NOT silently fall back to the database for locks. A silent fallback
   turns a visible outage into an invisible correctness risk, and this project exists partly to let
   the operator see failures.
7. **Idempotency** (`SRC-001 §5.3.2`, `SRC-002 §8.3.1`): the booking confirmation endpoint takes an
   `Idempotency-Key` header, and retrying the same key returns the original result rather than
   creating a second booking or a second charge.
8. **Recoverability** (`SRC-001 §7.5`): killing any container mid-request MUST NOT corrupt data,
   lose money, or leave a customer holding a seat they did not get. Containers are stateless
   (`SRC-002 §7.3`) — no local session state, no local file writes.
9. **Auditability** (`SRC-001 §7.6`): the system MUST be able to answer "who booked this seat and
   when" for any seat, at any time.

## Article V — Money & Payment

1. **Money is a reserved matter** (Art III.8). No model decides a price, a fee, a refund rule, or a
   currency.
2. **Store money as an integer in the currency's minor unit. Never a float.** Decimal at the
   boundary, integer in the persistence layer, formatted string at render time only. A float
   anywhere on the money path is a defect regardless of whether a test caught it.
3. **RULED 2026-08-14** (`SRC-003 OPEN-LOCALE-01`): the market is **India**, the currency is
   **INR**, the minor unit is **paise** at a ratio of **100**, and the timezone is
   **Asia/Kolkata**. Money is stored as an integer number of paise. **The ratio is a one-way door**
   — `SRC-001 §7.6` makes bookings permanent, so a currency reinterpreted later silently rewrites
   what every past customer paid. It stays a named configuration value rather than a literal
   scattered through the code, and it is never changed by inference.
   **Rounding is specified with a worked example** wherever a percentage meets an integer number of
   paise (`OPEN-PRICE-01`), because an unstated rounding rule is how two screens disagree about a
   total.
4. **Payment is collected before a booking is confirmed** (`SRC-001 §5.3.1`), and **a customer is
   never charged twice for one booking attempt** (`§5.3.2`), including on refresh or double-click.
5. **The v1 payment provider is simulated** — a real interface with real state transitions
   (`pending` → `authorized` → `captured` / `failed`) and an artificial delay, shaped so a real
   provider drops in behind it without a schema change. **(build-session ruled, pending an ADR under
   `GOAL_02`; the client proposed exactly this in `SRC-001 §10.19` and confirmed it on 2026-08-14.)**
   `OPEN-PAY-01` remains open for the eventual real provider.
6. **The simulated provider MUST NOT be reachable in a deployed environment without a visible,
   deliberate flag.** A simulated payment that looks real to a customer is the worst failure mode
   this article can produce.
7. **No card data ever touches this system** (`SRC-001 §9.5`). Not in a log, not in a database
   column, not in a test fixture, not in a seed script. This holds for the simulated provider too,
   because a fixture becomes a habit.
8. **Refunds are irreversible and therefore reserved.** `OPEN-CANCEL-01` and `OPEN-CANCEL-02` are
   open; no refund behaviour may be inferred from a cancellation window that has not been ruled.

## Article VI — Security, Roles & Privacy

1. **Authentication is our own: email and password, with JWT** (`SRC-002 §4.8`). Cognito MUST NOT be
   used.
2. **Passwords are hashed with a deliberately slow algorithm, off the event loop.** Compare even for
   an unknown email, so response timing does not disclose whether an account exists.
3. **RULED 2026-08-14** (`SRC-003 OPEN-ROLE-01`, reading `C-1`, **PROVISIONAL**): **four roles.**
   **guest** — browses, cannot hold or book. **customer** — an account is required to book.
   **manager** — **read only**, scoped to their assigned screens, twelve accounts across six halls.
   **admin** — everything, and a superset of manager.
   **There is no cinema-staff role and no door scanner** (`SRC-001 §4` erratum `E-1`). Entry is a
   manual check of the booking reference on the emailed receipt.
   The reading is `PROVISIONAL` because two of the client's own answers had to be reconciled;
   `SRC-003 C-1` records the alternative that was rejected.
   **Every privileged write belongs to the admin alone** (`SRC-003 OPEN-OPS-03`). A manager creates
   nothing, prices nothing and publishes nothing. A manager endpoint that performs a write is a
   defect against this article, not a feature. *(Folded into clause 3 rather than added as a new
   clause, so the numbering other documents already cite does not shift.)*
4. **Staff and management functions MUST NOT be reachable by customers** (`SRC-001 §7.4`).
   Authorisation is written once as a dependency and applied to a whole router — **one place, never
   per handler.** A per-handler check is the pattern that eventually misses one.
5. **A manager's authority is scoped to their own cinema** (`SRC-001 §4.4`). A manager reading
   another cinema's occupancy is a privilege breach, not a reporting feature, and needs a test
   asserting a **non-empty result for their own cinema and an empty or denied result for another** —
   a test asserting only "denied" passes against a query that returns nothing for anybody.
6. **Every privileged action writes an audit row in the same transaction as the change it records.**
   Either both land or neither does. `SRC-001 §7.6` makes this the mechanism, not a nicety.
7. **A privilege that cannot be exercised must fail loudly.** A cross-role capability that returns
   an empty result and a 200 is indistinguishable from a working one. Every such capability needs a
   test asserting a **non-empty, non-zero** result.
8. **Secrets live in the environment, and in AWS in SSM Parameter Store** (`SRC-002 §5.4.3`).
   Secrets Manager MUST NOT be used. **Never commit a credential**; `/tt` scans the staged diff
   before every push.
9. **WITHDRAWN 2026-08-14** — there is no TMDB API key, because there is no TMDB integration
    (`SRC-002 §10` erratum `E-2`). The clause number is retained rather than reused so that nothing
    citing `Art VI.9` silently comes to mean something else.
10. **Attribution is still owed if the material is licensed.** `SRC-002 §10.2`'s footer credit was a
    TMDB API licence condition and that integration is gone — but the client supplies the posters
    and titles themselves, and if any of it originates from TMDB or another licensed source the
    obligation returns. Open as `OPEN-ATTRIB-01`. **No licensed image or synopsis enters this
    product until that row is closed.**

## Article VII — AI Agent Guardrails (the honesty floor)

1. **No invented evidence.** Unverified means writing the word *unverified*. A number nobody ran is
   not a result.
2. **Worst number first.** Every rate carries its count. "Most tests pass" is not a report.
3. **A gap stays a gap.** An `OPEN` row filled in with something plausible is the cardinal sin of
   this project. Escalate; never invent.
4. **Respect one-way doors.** Anything irreversible stops and asks, at any confidence level.
5. **The log is the memory.** Nothing important lives only in a chat window. A session that ends
   without `/tt` has lost its memory.
6. **Scope as written.** Not the scope that would be more impressive, more complete, or easier.
7. **The writer never verifies its own work.** Where no second human exists, the substitute is a
   fresh zero-context session, and **the substitution is recorded** rather than passed off as
   independent review.
8. **Report what the client asked to be told.** `SRC-002 §5.4.1` and `§13.6` require the build
   session to say when something will not fit in 1 GB of RAM rather than quietly working around it.
   Silently absorbing a constraint violation breaches this article.
9. **Explain the way the client asked to be explained to** (`SRC-002 §2`): at the level of someone
   who can code but has never run production infrastructure; **no figures of speech, no analogies,
   no metaphors**; short paragraphs over bullet dumps.

## Article VIII — Operations & Deployment

1. **The build session writes no infrastructure.** `SRC-002 §6.3` reserves to the client: Terraform
   and CloudFormation, ECS task and service definitions, ALB / target group / listener / security
   group configuration, VPC and subnet layout, GitHub Actions and any CI/CD pipeline, CloudWatch
   alarms and dashboards, and any `aws` CLI command that creates infrastructure.
2. **The build session creates nothing in AWS.** As of 2026-08-14 the client has supplied read
   credentials so the build session can **inspect what the client built and check it against the
   specification**. That permission is **read-only and explicit**: describe, list and get. **No
   create, no modify, no delete, at any confidence, until the client says otherwise in writing.**
   Destructive AWS actions are always human.
3. **Consequence, stated every time it matters:** the build session has never observed this
   application running in AWS. Every statement it makes about AWS runtime behaviour is
   **reasoned, not observed**, and MUST be labelled that way.
4. **In exchange for Art VIII.1 the build session owes advance notice.** Every AWS dependency is
   added to `docs/30 Deployment/AWS_PREP_QUEUE.md` with a *needed by* stage **and** said in chat,
   early enough to be prepared while code is still being written. **Never announce a dependency on
   the day it blocks.**
5. **`SRC-002 §6.4` is a deliverable, not a courtesy.** For each Zone C item the build session
   produces what to build, what the application expects of it (ports, health check paths, env vars,
   IAM permissions), acceptance criteria, and two or three common mistakes. **`SRC-002 §6.5`: do not
   give the answer. Give the specification and let the client fail against it.**
6. **Everything must fit AWS Free Tier** (`SRC-002 §5.1`). EKS, Fargate, NAT Gateway, Secrets
   Manager, Managed Grafana and OpenSearch MUST NOT be designed around (`§5.3`). Kubernetes, service
   meshes and any managed service outside `SRC-002 §4` require the client's permission first
   (`§4.12`).
7. **Roughly 1 GB of RAM covers every container together** (`SRC-002 §5.4.1`), on a host that also
   runs an operating system, a Docker daemon and an ECS agent. Explicit memory limits are set on
   every container. The final image targets **under 250 MB** with a multi-stage build and a slim base
   (`§5.4.2`), because ECR's free tier holds 500 MB total.
8. **Twelve-factor configuration** (`SRC-002 §7.1`): every setting comes from an environment
   variable, and the application **crashes on startup with a clear message** when a required one is
   missing. A missing key makes the dependent story `Blocked`, never stubbed.
9. **Migrations run as a separate step, never on application boot** (`SRC-002 §7.8`).
10. **Health endpoints behave differently on purpose** (`SRC-002 §7.4`): `/health/live` returns 200
    if the process is alive; `/health/ready` returns 503 when the database or Redis is unreachable.
    Collapsing them into one endpoint defeats the reason they exist.
11. **Graceful shutdown** (`SRC-002 §7.5`): on SIGTERM, stop accepting new requests, finish in-flight
    ones, **release the Redis locks held by that instance**, then exit.
12. **Structured logging** (`SRC-002 §5.4.5`, `§7.6`): JSON to stdout, never a file on disk, with a
    request id propagated through every log line including worker jobs triggered by that request.
13. **No NAT Gateway exists** (`SRC-002 §5.3`, `§5.4.4`). The application must be able to run in a
    public subnet behind strict security groups, and **every place it needs outbound internet access
    is documented** — TMDB, S3, SQS and SSM at minimum.
14. **The deployed environment is never called production** in any document while it runs without
    TLS.
15. **Zone B is written to be read** (`SRC-002 §6.2`). Every line in a Dockerfile, entrypoint,
    health check, config validator or shutdown handler that exists for a production reason carries a
    comment saying **what breaks without it**.

## Article IX — Quality & Verification

1. **Definition of Done.** A failing test first, written from the acceptance criterion. Then minimal
   code. Then edge and negative cases. Done only when the acceptance criterion passes, the suite is
   green, **the concurrency gate is still green**, and a handover is written.
2. **Never fake, skip, `xfail`, comment out or delete a test to reach green.** A red gate blocks —
   mark the story `Blocked` with a note and surface it. A story marked `Done` with no supporting
   commit or with a red gate is a **fake green**, and a suspected fake green is a stop-the-line
   finding.
3. **Acceptance criteria are binary.** "The seat map works" is not an acceptance criterion. "50
   concurrent POSTs to `/api/showtimes/{id}/hold` for seat `A-12` return exactly one 200 and 49
   409s" is.
4. **Every rule that computes a number states the rule, its inputs, and a worked example with the
   expected answer.** A specification that computes money or time and gives no worked example cannot
   produce a binary test.
5. **A test that reads the wall clock is a defect.** Time is injected. A gate that goes red at
   midnight with no code change has told you about your test, not your system.
6. **Two layers of checking.** The cheap mechanical layer is a consistency script that answers one
   question — does every cross-reference actually resolve? It ships `--selftest`, which **plants a
   real violation of each rule and requires the check to fire**, measured by delta so it still works
   on a repository that is already red. The expensive layer is the pre-code design review
   (`docs/12 DesignReview/`), which exists because the cheap layer is blind to two documents that
   each read perfectly well alone and contradict each other.
7. **The writer never verifies its own work** (Art VII.7). Irreversible calls and every completed
   document are graded by a fresh zero-context session.
8. **Waiving any quality check is reserved to the client** (Art III.8). Adopting a stricter option is
   not a waiver.

## Article X — Open Decisions Register (explicitly NOT legislated here)

Listed as open. Deliberately not decided. **No timeout defaults past a reserved matter** — if the
approver is unavailable, that work stops.

**Owner is the client on every row.** The build session raised them; it may not close them.

Rows `OPEN-SCALE-01` … `OPEN-OPS-03` are the client's own thirty questions from `SRC-001 §10`,
carried here unchanged. Rows `OPEN-NAME-01` onward were raised by the build session while drafting
this Constitution.

---

> ## ✅ ADJUDICATED 2026-08-14 — read `SRC-003`, not the tables below
>
> **All 40 rows were ruled by the client on 2026-08-14** and are filed verbatim in
> `docs/00 SourceOfTruth/SRC-003_client_rulings_2026-08-14.md`. **`SRC-003` is the authority on
> every answer.** The question tables that follow are retained unedited as the record of *what was
> asked and how* — they are history, not live state.
>
> | Outcome | Count |
> |---|---|
> | `RULED` — binding | 36 |
> | `ASSUMED` — client said "you pick"; never hardens into a constraint | 3 |
> | `DEFERRED` — `OPEN-TLS-01`, the client is sourcing a domain | 1 |
>
> **Sixteen errata** were filed as a result — ten against `SRC-001`, six against `SRC-002`. Both
> sources' hashes moved and the invalidation is adjudicated in `fingerprints.json`.
>
> **Three rulings carry a build-session reading rather than a literal answer**, each recorded with
> the alternative it rejected and each `PROVISIONAL` — one message from the client reverses any of
> them: the role set (`SRC-003 C-1`), one cinema or several (`C-2`), and whether the sales cut-off
> is 15 minutes before or after the advertised start (`OPEN-BOOK-03`).
>
> **The largest change: TMDB is gone.** `SRC-002 §10` is withdrawn in full. The administrator
> creates movies by hand. Nothing in this system runs on a schedule any more.

### X.0 — Rows still open

These three were **raised by the rulings themselves** and are not closed. Each is reserved.

| ID | Question | Class |
|---|---|---|
| `OPEN-TLS-01` | *(carried forward, `DEFERRED`)* The client is looking for a domain. Until one exists with an ACM certificate, the session cookie's `Secure` flag stays off in the deployed environment and Art VIII.14 keeps that environment un-named as production. | reserved: product |
| `OPEN-ATTRIB-01` | The TMDB integration is gone, but the client will supply posters and titles themselves. If that material comes from TMDB or any other licensed source, the attribution obligation still applies. Where does it come from? | reserved: legal |
| `OPEN-SHOWCANCEL-01` | `OPEN-OPS-03` names *"cancel a show"* as an admin action; `OPEN-CANCEL-02` said to forget cinema-cancelled shows. If an admin withdraws a showtime that already has bookings, what happens to those bookings and to the money? | reserved: money, irreversible |
| `OPEN-EMAILFAIL-01` | The emailed receipt is now the customer's only proof of purchase and their only way into the hall. What happens when SES fails *after* payment is captured? | reserved: product |

*(Four rows. `OPEN-TLS-01` is carried forward; the other three are new.)*

---

**Historical record — the questions as they were asked on 2026-08-14.** Every row below is now
answered in `SRC-003`. Do not read a `Recommendation` cell as live guidance.

### X.1 — Blocking, in order of what they hold up

| ID | Question | Class | Recommendation |
|---|---|---|---|
| `OPEN-NAME-01` | The client's exact full name for the ratification block, and a backup decider (`NONE — accepted` is a valid written answer). **Until this lands this Constitution is UNADOPTED and every ADR filed carries a "recorded while ungoverned" caveat.** | reserved: governance | — |
| `OPEN-LOCALE-01` | *(`SRC-001 §10.4`)* Which country and city do we launch in, and which currency? **Blocks the data model, not just the UI**: Art V.3 forbids hardcoding a minor-unit ratio, and `SRC-002 §10.4`'s TMDB `region` parameter needs the same answer. | reserved: product | None offered. This is the client's market. |
| `OPEN-PAY-02` | *(`SRC-001 §10.19`)* Is a simulated payment step acceptable for v1? **Answered yes on 2026-08-14**; row stays open until an ADR files it and the client's answer lands in `SRC-003`. | reserved: money | Simulated provider with a real interface — Art V.5. |
| `OPEN-ROLE-01` | **`SRC-001 §4` and `SRC-002 §3.1` disagree on how many roles exist** — five against one. Per Art II.2 the build session may not pick. This decides the auth model, the admin surface, and whether `SRC-001 §5.5.3` (staff ticket validation) is in v1 at all. | reserved: scope | Model five roles in the schema from day one; expose only the ones a ruled phase needs. Expanding a role set later is a rewrite; collapsing one is a migration. |
| `OPEN-SCOPE-01` | **Four `SRC-001` requirements have no phase in `SRC-002 §12`**: staff ticket validation (`§5.5.3`), per-cinema manager scoping (`§4.4`), customer cancellation (`§5.4.3`), and management reporting (`§5.5.2`). Confirmed on 2026-08-14 as "build the seven phases, extend after" — the row stays open until the extension phases are actually written down, because an undocumented intention is not a plan. | reserved: scope | Phases 8 and 9, specified now, built after Phase 7. |
| `OPEN-QUEUE-01` | **`SRC-002 §4.5` requires an SQS-consuming worker; `SRC-002 §5.4.1` prefers RQ or Dramatiq, which are Redis brokers.** These are two architectures. Also unresolved: what stands in for SQS in local development, which is a new dependency and `SRC-002 §13.1` requires asking. | reserved: scope (a new dependency) | A thin queue interface with an SQS implementation for AWS. The local stand-in needs the client's permission before it is added. |
| `OPEN-EMAIL-01` | **`SRC-002 §8.5.1` requires the worker to send a confirmation email; `SRC-001 §5.3.4` requires the customer to receive one. No approved service in `SRC-002 §4` can send mail**, and `§4.12` forbids adding one unasked. As specified, this requirement cannot be built. | reserved: scope (a new managed service) | SES is the obvious candidate and is outside the approved list. Needs a yes before Phase 5 starts. |
| `OPEN-PROC-01` | **`SRC-002 §12` implies four long-running processes** — API, worker, scheduler, frontend — inside roughly 1 GB shared with an OS, a Docker daemon and an ECS agent. Art VII.8 requires this be said rather than absorbed. | reserved: product | Fold the scheduler into an EventBridge trigger against the admin HTTP endpoint (`SRC-002 §10.6.1` already requires that endpoint), and serve the built frontend from a small static container. Three processes, not four. *(reasoned, not observed)* |

### X.2 — Scope and scale *(the client's `SRC-001 §10`, questions 1–4)*

| ID | Question | Class |
|---|---|---|
| `OPEN-SCALE-01` | How many cinemas, and how many screens per cinema, at launch? | product |
| `OPEN-SCALE-02` | What is the largest screen, in number of seats? **Not cosmetic** — it sets the seat-map payload size and the cache entry size. | product |
| `OPEN-SCALE-03` | What is the realistic peak, in customers booking at the same minute? Sets what the load test must prove. | product |
| `OPEN-LOCALE-01` | *(listed in X.1 — it blocks the data model)* | reserved |

### X.3 — Seat and screen setup *(questions 5–8)*

| ID | Question | Class |
|---|---|---|
| `OPEN-SEAT-01` | Do screens have different seat categories, for example recliner, premium, standard? `SRC-001 §5.2.3` says they are priced differently, so the answer is probably yes and the category list is still unknown. | product |
| `OPEN-SEAT-02` | Are there wheelchair accessible seats that must be marked and reserved as such? **Has an accessibility and possibly a legal dimension**, so it is not a display flag. | reserved: legal |
| `OPEN-SEAT-03` | Are there seats sold only as a pair, for example couple seats? Changes the lock from per-seat to per-group, which is a different concurrency problem. | product |
| `OPEN-SEAT-04` | Should we prevent a customer leaving a single empty seat between bookings? A rule that can make a valid selection fail at confirmation time, so it must be enforced where the seat map is drawn, not only at checkout. | product |

### X.4 — Booking rules *(questions 9–14)*

| ID | Question | Class |
|---|---|---|
| `OPEN-HOLD-01` | How long are seats held while the customer pays? **The client assumed 7 minutes in `SRC-001 §10.9` and `SRC-002 §8.1.1` states 7 minutes as a requirement.** The assumption has hardened into a spec without ever being confirmed — exactly the drift Art II.7 exists to catch. | product |
| `OPEN-BOOK-01` | Maximum number of seats in one booking? | product |
| `OPEN-BOOK-02` | Can a guest book without an account, or is login required? `SRC-001 §4.1` grants guests browsing only, but never says booking requires an account. Decides whether an order can exist without a user row. | product |
| `OPEN-BOOK-03` | How long before showtime do sales stop? | product |
| `OPEN-CANCEL-01` | Can a customer cancel, until when, and is the refund full or partial? | **reserved: money** |
| `OPEN-CANCEL-02` | What happens when the cinema cancels a show — automatic refunds? | **reserved: money, irreversible** |

### X.5 — Pricing *(questions 15–17)*

| ID | Question | Class |
|---|---|---|
| `OPEN-PRICE-01` | Does price vary by seat category, time of day, day of week, or movie? Decides whether pricing is a column or a table. | **reserved: money** |
| `OPEN-PRICE-02` | Discount codes, student pricing, convenience fees? | **reserved: money** |
| `OPEN-PRICE-03` | Is tax shown separately on the ticket? Tax is rarely reversible once bookings exist. | **reserved: money, legal** |

### X.6 — Payment *(questions 18–19)*

| ID | Question | Class |
|---|---|---|
| `OPEN-PAY-01` | Which payment provider, and does the client already have an account? Open for the real provider even though v1 is simulated. | **reserved: money** |
| `OPEN-PAY-02` | *(listed in X.1 — answered 2026-08-14, awaiting its ADR)* | reserved |

### X.7 — Movie data *(questions 20–23)*

| ID | Question | Class |
|---|---|---|
| `OPEN-TMDB-01` | Which region should listings be pulled for? Same answer as `OPEN-LOCALE-01`, needed by `SRC-002 §10.4`. | product |
| `OPEN-TMDB-02` | Should upcoming releases be visible before tickets go on sale? `SRC-001 §5.1.2` requires showing them; this asks whether that happens before a showtime exists. | product |
| `OPEN-TMDB-03` | Who approves an imported movie — the manager or the administrator? `SRC-001 §5.5.4` says administrator, `§5.6.2` says "a staff member". A source conflict inside one document. | product |
| `OPEN-TMDB-04` | May imported details be overridden — a different poster, a local title? Decides whether the sync job may overwrite a field a human edited. Getting this wrong destroys human work on a daily schedule. | product |

### X.8 — Tickets and entry *(questions 24–25)*

| ID | Question | Class |
|---|---|---|
| `OPEN-TICKET-01` | QR code, numeric reference, or both? `SRC-002 §8.5.1` already assumes a QR code. | product |
| `OPEN-TICKET-02` | Does staff need an offline way to validate tickets if the internet drops at the door? **An offline validation path is a different security model**, not a fallback screen. | product |

### X.9 — Reporting *(questions 26–27)*

| ID | Question | Class |
|---|---|---|
| `OPEN-REPORT-01` | What does management need daily, and what weekly? | product |
| `OPEN-REPORT-02` | Is an export needed, for example to a spreadsheet? An export of booking data is a data-protection surface, not only a feature. | product |

### X.10 — Operations *(questions 28–30)*

| ID | Question | Class |
|---|---|---|
| `OPEN-OPS-01` | Who receives alerts if the system goes down? With no alerting configured, the honest answer is "nobody", and that belongs written down as an accepted risk rather than left as an unnoticed hole. | product |
| `OPEN-OPS-02` | How long must booking records be kept? A retention floor is a legal question and a storage cost. | **reserved: legal** |
| `OPEN-OPS-03` | Are staff activity logs needed — who changed a price? Art VI.6 already requires an audit row per privileged action; this asks whether the client needs to *read* them. | product |

### X.11 — Raised by the build session

| ID | Question | Class | Recommendation |
|---|---|---|---|
| `OPEN-MODEL-01` | What code and data may enter an AI model, and which vendors become sub-processors once real customer and payment data exists. | reserved: legal | — |
| `OPEN-TLS-01` | The deployed environment has an ALB (`SRC-002 §4.11`), so TLS is available — unlike the prior project. Does the client intend to terminate TLS at it, and with which certificate? Until answered, the session cookie's `Secure` flag has no ruled value and Art VIII.14 keeps the environment un-named as production. | reserved: product | Terminate at the ALB with an ACM certificate. ACM is free for ALB use and is not on the forbidden list. *(reasoned, not observed)* |
| `OPEN-SEED-01` | `SRC-002 §6.1.6` requires seed data with sample cinemas, screens and showtimes. Those are invented product content — cinema names, screen layouts, film times. Art VII.3 forbids the build session inventing content the client will see and treat as real. | reserved: product identity | Obviously-fictional names, or the client supplies the real ones. A one-message question. |
| `OPEN-AWSREAD-01` | The read-only AWS credentials supplied on 2026-08-14 — which account, which region, and is any inspection of a live environment holding real customer data in scope, or development only? | reserved: secrets | Development only until stated otherwise. Art VIII.2 already forbids any write. |

## Article XI — Repository Reading Rules

1. **For decision status, trust the ledger. For document versions, trust the files on disk. For
   paths, trust the repository tree** — never a path quoted in prose.
2. `docs/` holds the delivery document set, numbered in **dependency order**, not generation order.
   `00` is frozen input; `01` is the decision record; `02`→`06` is the derivation chain; `07`→`13`
   is proof and audit; `14`+ is lifecycle. **Two folders are written out of numeric order on
   purpose**: `05 B DesignSystem` before `03 PRD`, because the PRD's screens bind to its tokens; and
   `11 Journeys` before `05 Bible`, because journeys find the seams a per-screen specification
   misses.
3. The folder set is **fixed**. Its contents are not: a folder may hold more or fewer documents than
   the prior project's did, but no folder is added, removed or renumbered.
4. The root files are the working canon: `CLAUDE.md` (what a session reads first), `GOTCHAS.md` (the
   trap ledger), `PROGRESS.md` (the append-only session log), `COORDINATION.md` (the lane map),
   `handoffs/` (what `/tt` writes and `/ss` reads back), `goals/` (the unit of work).
5. **`/ss` at the start of every session; `/tt` at the end of every session.** A session that ends
   without `/tt` has lost its memory.
6. **GitHub is the source of truth.** `github.com/AniruddhasGit/FrontRow`, **private**.
   *(Moved 2026-08-14 on the client's instruction, from `github.com/AniruddhaDynpro/FrontRow`.
   The old remote is retained locally as `dynpro` so no history is stranded. The RULE in this
   clause is unchanged — only the identifier of which repository it points at, which is a fact
   the client stated, not an amendment a model made. Records written before that date name the
   old URL and are correct as written; `FR-ADR-071` in particular is APPROVED and immutable
   under Art III.3 and is NOT edited.)* Nothing important lives
   in a chat history, on one laptop, or in one model's context. The test of this rule: a session
   starting cold on a different machine, under a different account, with `/ss` and the repository
   alone, must reach full situational awareness.

## Article XII — Amendment & Ratification

1. Amending this Constitution is itself a **reserved matter.** A model may propose; only the named
   human adopts.
2. Amendments land as a superseding ADR plus a version bump here — never as a silent edit.
3. The version string `frontrow-constitution@0.1.0` is stamped on every governed decision. Use that
   exact string everywhere; two strings that drift by one word invalidate every record that carried
   the wrong one.

---

## Ratification block

```
STATUS:       ADOPTED
ADOPTED BY:   Aniruddha Jathar
ROLE:         client, developer, money-signer and rules-signer — all four
BACKUP:       NONE — stated affirmatively, not left blank
DATE:         2026-08-14
VERSION:      frontrow-constitution@0.1.0
SCOPE:        The FrontRow project only.
SOURCE:       SRC-003 OPEN-NAME-01 — "Aniruddha Jathar is my name and i will always be
              the one building"
```

**No ADR carries the "recorded while ungoverned" caveat**, because the Constitution was adopted
before the first record was filed.

> **The consequence of one person holding all four roles, stated plainly.** The decision queue that
> this method relies on never forms, because there is nobody it is for and no delay in which a bad
> answer becomes visible. Article IX.7 is therefore not a formality on this project — a fresh
> zero-context session grading every irreversible call is the **only** second opinion that exists
> here, and where it is skipped, nothing catches the mistake.
